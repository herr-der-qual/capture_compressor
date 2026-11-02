"""Compressing one finished recording: encode, verify, then replace or keep the original."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from . import decisions, ffmpeg_tools, file_operations
from .settings import Settings
from .skip_list import SkipList

logger = logging.getLogger(__name__)
BYTES_PER_MEGABYTE = 1_000_000


@dataclass(frozen=True)
class Tools:
    ffmpeg: str
    ffprobe: str
    encoder: str


class CompressionJob:
    def __init__(
        self,
        source: Path,
        settings: Settings,
        tools: Tools,
        skip_list: SkipList,
        notify: Callable[[str], None],
        should_abort: Callable[[], bool],
    ) -> None:
        self.source = source
        self.settings = settings
        self.tools = tools
        self.skip_list = skip_list
        self.notify = notify
        self.should_abort = should_abort
        self.source_status = source.stat()
        self.partial = decisions.partial_path_for(source)
        self.compressed = decisions.compressed_path_for(source)

    @property
    def identity(self) -> str:
        return decisions.file_version_identity(
            self.source, self.source_status.st_size, self.source_status.st_mtime
        )

    def probe_source_duration(self) -> float | None:
        duration = ffmpeg_tools.probe_duration(self.tools.ffprobe, self.source)
        if duration is None:
            logger.warning("Skipping %s: ffprobe cannot read it", self.source.name)
            self.skip_list.add(self.identity)
        return duration

    def run(self, source_duration: float) -> None:
        if self._encode(source_duration):
            self._apply(self._verify(source_duration))

    def _encode(self, source_duration: float) -> bool:
        logger.info(
            "Compressing %s (%.1f MB, %.1fs) with %s quality %d",
            self.source.name, self.source_status.st_size / BYTES_PER_MEGABYTE,
            source_duration, self.tools.encoder, self.settings.quality,
        )
        succeeded, ffmpeg_output = ffmpeg_tools.encode(
            self.tools.ffmpeg, self.source, self.partial, self.tools.encoder,
            self.settings.quality, should_abort=self.should_abort,
        )
        if succeeded:
            return True
        file_operations.delete_if_exists(self.partial)
        if ffmpeg_output != ffmpeg_tools.ABORTED:
            logger.error("ffmpeg failed on %s:\n%s", self.source.name, ffmpeg_output)
            self.notify(f"Failed to compress {self.source.name}, see log")
        return False

    def _verify(self, source_duration: float) -> decisions.Verdict:
        return decisions.verify_compression(
            self.source_status.st_size,
            self.partial.stat().st_size,
            source_duration,
            ffmpeg_tools.probe_duration(self.tools.ffprobe, self.partial),
        )

    def _apply(self, verdict: decisions.Verdict) -> None:
        if verdict.action == "replace":
            self._replace_original(verdict)
            return
        file_operations.delete_if_exists(self.partial)
        if verdict.action == "keep_original":
            self.skip_list.add(self.identity)
            logger.info("Kept original %s: %s", self.source.name, verdict.reason)
        else:
            logger.error("Verification failed for %s: %s", self.source.name, verdict.reason)
            self.notify(f"Verification failed for {self.source.name}: {verdict.reason}")

    def _replace_original(self, verdict: decisions.Verdict) -> None:
        compressed_size = self.partial.stat().st_size
        os.replace(self.partial, self.compressed)
        # Keep the recording date so sorting by date still works.
        os.utime(self.compressed, (self.source_status.st_atime, self.source_status.st_mtime))
        file_operations.delete_file(self.source, permanently=self.settings.permanent_delete)
        logger.info(
            "Done %s -> %s (%.1f MB, %s); original %s",
            self.source.name, self.compressed.name, compressed_size / BYTES_PER_MEGABYTE,
            verdict.reason,
            "deleted" if self.settings.permanent_delete else "moved to Recycle Bin",
        )

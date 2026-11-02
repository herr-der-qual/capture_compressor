"""Background engine: watches the folder and compresses finished recordings one by one."""

from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable

from . import decisions, ffmpeg_tools, status
from .compression_job import CompressionJob, Tools
from .folder_watcher import FolderWatcher
from .recording_queue import RecordingQueue
from .settings import Settings
from .skip_list import SkipList
from .status import Status

logger = logging.getLogger(__name__)

CHECK_INTERVAL_SECONDS = 1.0
WORKER_STOP_TIMEOUT_SECONDS = 10


def _same_folder(first: str | Path, second: str | Path) -> bool:
    return os.path.normcase(str(first)) == os.path.normcase(str(second))


class CompressionEngine:
    def __init__(
        self,
        settings: Settings,
        on_status_change: Callable[[Status], None] = lambda new_status: None,
        notify: Callable[[str], None] = lambda message: None,
    ) -> None:
        self.settings = settings
        self.on_status_change = on_status_change
        self.notify = notify
        self.skip_list = SkipList()
        self.queue = RecordingQueue(self.skip_list)
        self.watcher = FolderWatcher(self.add_recording)
        self.tools: Tools | None = None
        self._wake_up = threading.Event()
        self._stopping = threading.Event()
        self._worker: threading.Thread | None = None
        self._paused = False
        self._current_file = ""
        self._error = ""
        self._status = Status()

    # ---- public interface -------------------------------------------------

    @property
    def status(self) -> Status:
        return self._status

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def active_encoder(self) -> str:
        return self.tools.encoder if self.tools else ""

    def start(self) -> None:
        self._choose_tools()
        self._start_watching()
        self._worker = threading.Thread(target=self._work, name="compressor", daemon=True)
        self._worker.start()

    def stop(self) -> None:
        self._stopping.set()
        self._wake_up.set()
        self.watcher.stop()
        if self._worker:
            self._worker.join(timeout=WORKER_STOP_TIMEOUT_SECONDS)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        logger.info("Paused" if paused else "Resumed")
        self._publish_status()
        self._wake_up.set()

    def apply_settings(self, updated: Settings) -> None:
        previous, self.settings = self.settings, updated
        if (previous.encoder, previous.ffmpeg_path) != (updated.encoder, updated.ffmpeg_path):
            self._choose_tools()
        if not _same_folder(previous.watch_folder, updated.watch_folder):
            self.queue.clear()
            self.watcher.stop()
            self._start_watching()
        self._publish_status()

    def add_recording(self, path: Path) -> None:
        if not decisions.is_uncompressed_recording(path):
            return
        if not _same_folder(path.parent, self.settings.watch_folder):
            return
        if self.queue.add(path):
            logger.info("Queued %s", path.name)
        self._publish_status()
        self._wake_up.set()

    def is_idle(self) -> bool:
        return len(self.queue) == 0 and not self._current_file

    # ---- setup ------------------------------------------------------------

    def _choose_tools(self) -> None:
        """Find ffmpeg and make sure the chosen encoder really works on this machine."""
        self._error = ""
        self.tools = None
        try:
            ffmpeg, ffprobe = ffmpeg_tools.find_ffmpeg_and_ffprobe(self.settings.ffmpeg_path)
        except ffmpeg_tools.FfmpegNotFound as error:
            self._report_error(str(error))
            return
        encoder = self._working_encoder(ffmpeg)
        if encoder:
            self.tools = Tools(ffmpeg, ffprobe, encoder)
        self._publish_status()

    def _working_encoder(self, ffmpeg: str) -> str | None:
        wanted = self.settings.encoder
        failure = ffmpeg_tools.test_encoder(ffmpeg, wanted)
        if failure is None:
            logger.info("Using encoder %s (%s)", wanted, ffmpeg)
            return wanted
        logger.error("Encoder %s does not work: %s", wanted, failure)
        fallback = decisions.FALLBACK_ENCODER
        if wanted != fallback and ffmpeg_tools.test_encoder(ffmpeg, fallback) is None:
            message = f"{wanted} is not available ({failure}). Using {fallback} (CPU) instead."
            logger.warning(message)
            self.notify(message)
            return fallback
        self._report_error(f"no working encoder: {failure}")
        return None

    def _start_watching(self) -> None:
        folder = Path(self.settings.watch_folder)
        if not folder.is_dir():
            self._report_error(f"folder not found: {folder}")
            return
        self.watcher.start(folder)

    # ---- worker -----------------------------------------------------------

    def _work(self) -> None:
        while not self._stopping.is_set():
            self._wake_up.wait(CHECK_INTERVAL_SECONDS)
            self._wake_up.clear()
            if self._stopping.is_set():
                break
            finished_recording = self.queue.take_finished_recording()
            if finished_recording and self._can_compress():
                self._compress_safely(finished_recording)
                self._wake_up.set()  # look for the next one right away
            self._publish_status()

    def _can_compress(self) -> bool:
        return not self._paused and self.tools is not None

    def _compress_safely(self, source: Path) -> None:
        try:
            self._compress(source)
        except Exception:  # one bad file must not stop the worker
            logger.exception("Unexpected error while processing %s", source)
        finally:
            self._current_file = ""

    def _compress(self, source: Path) -> None:
        job = CompressionJob(
            source, self.settings, self.tools, self.skip_list,
            notify=self.notify, should_abort=self._stopping.is_set,
        )
        source_duration = job.probe_source_duration()
        if source_duration is None:
            return
        self._current_file = source.name
        self._publish_status()
        job.run(source_duration)

    # ---- status -----------------------------------------------------------

    def _report_error(self, error: str) -> None:
        logger.error("%s", error)
        self._error = error
        self.notify(error)
        self._publish_status()

    def _publish_status(self) -> None:
        new_status = Status(
            state=status.decide_state(self._current_file, self._error, self._paused),
            current_file=self._current_file,
            queued_count=len(self.queue),
            error=self._error,
            active_encoder=self.active_encoder,
        )
        if new_status != self._status:
            self._status = new_status
            self.on_status_change(new_status)

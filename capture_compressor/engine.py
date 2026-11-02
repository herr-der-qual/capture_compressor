"""Background engine: watch the folder, wait for finished recordings, compress them."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from . import fileutil, logic, media
from .config import Settings, SkipList

log = logging.getLogger(__name__)

POLL_SECONDS = 1.0
STABLE_CHECKS = 3  # size unchanged for this many polls before we touch a file


@dataclass(frozen=True)
class Status:
    state: str = "idle"  # idle | compressing | paused | error
    current: str = ""
    queued: int = 0
    error: str = ""
    encoder: str = ""

    def text(self) -> str:
        if self.state == "error":
            return f"Error: {self.error}"
        if self.state == "paused":
            s = "Paused"
        elif self.state == "compressing":
            s = f"Compressing {self.current}"
        else:
            s = "Idle"
        if self.queued:
            s += f" - {self.queued} queued"
        return s


@dataclass
class _Pending:
    size: int = -1
    stable: int = 0


class _Handler(FileSystemEventHandler):
    def __init__(self, engine: "Engine") -> None:
        self.engine = engine

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.engine.enqueue(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.engine.enqueue(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.engine.enqueue(Path(event.dest_path))


class Engine:
    def __init__(
        self,
        settings: Settings,
        on_status: Callable[[Status], None] | None = None,
        on_notify: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.on_status = on_status or (lambda s: None)
        self.on_notify = on_notify or (lambda m: None)
        self.skip = SkipList()
        self._lock = threading.RLock()
        self._pending: dict[str, _Pending] = {}
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._paused = False
        self._observer: Observer | None = None
        self._thread: threading.Thread | None = None
        self._status = Status()
        self._current = ""  # file being compressed right now
        self.ffmpeg = self.ffprobe = ""
        self.encoder = ""

    # ---- public API -------------------------------------------------------

    @property
    def status(self) -> Status:
        return self._status

    @property
    def paused(self) -> bool:
        return self._paused

    def start(self) -> None:
        self._prepare_tools()
        self._start_watching()
        self._thread = threading.Thread(target=self._worker, name="compressor", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()
        self._stop_watching()
        if self._thread:
            self._thread.join(timeout=10)

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        log.info("Paused" if paused else "Resumed")
        self._publish()
        self._wake.set()

    def apply_settings(self, new: Settings) -> None:
        old, self.settings = self.settings, new
        if (old.encoder, old.ffmpeg_path) != (new.encoder, new.ffmpeg_path):
            self._prepare_tools()
        if os.path.normcase(old.watch_folder) != os.path.normcase(new.watch_folder):
            with self._lock:
                self._pending.clear()
            self._stop_watching()
            self._start_watching()
        self._publish()

    def enqueue(self, path: Path) -> None:
        if not logic.is_candidate(path):
            return
        if os.path.normcase(str(path.parent)) != os.path.normcase(self.settings.watch_folder):
            return
        with self._lock:
            if str(path) not in self._pending:
                log.info("Queued %s", path.name)
                self._pending[str(path)] = _Pending()
        self._publish()
        self._wake.set()

    def is_idle(self) -> bool:
        with self._lock:
            return not self._pending and not self._current

    # ---- setup ------------------------------------------------------------

    def _prepare_tools(self) -> None:
        """Find ffmpeg and make sure the chosen encoder really works on this machine."""
        self._set_error("")
        try:
            self.ffmpeg, self.ffprobe = media.resolve_tools(self.settings.ffmpeg_path)
        except media.FfmpegNotFound as e:
            log.error("%s", e)
            self.encoder = ""
            self._set_error(str(e))
            self.on_notify(str(e))
            return
        wanted = self.settings.encoder
        err = media.test_encoder(self.ffmpeg, wanted)
        if err is None:
            self.encoder = wanted
            log.info("Using encoder %s (%s)", wanted, self.ffmpeg)
            return
        log.error("Encoder %s does not work: %s", wanted, err)
        if wanted != logic.FALLBACK_ENCODER and media.test_encoder(
            self.ffmpeg, logic.FALLBACK_ENCODER
        ) is None:
            self.encoder = logic.FALLBACK_ENCODER
            msg = f"{wanted} is not available ({err}). Using {logic.FALLBACK_ENCODER} (CPU) instead."
            log.warning(msg)
            self.on_notify(msg)
        else:
            self.encoder = ""
            self._set_error(f"no working encoder: {err}")
            self.on_notify(f"No working encoder: {err}")

    def _start_watching(self) -> None:
        folder = Path(self.settings.watch_folder)
        if not folder.is_dir():
            log.error("Watch folder does not exist: %s", folder)
            self._set_error(f"folder not found: {folder}")
            return
        observer = Observer()
        observer.schedule(_Handler(self), str(folder), recursive=False)
        observer.start()
        self._observer = observer
        log.info("Watching %s", folder)
        # Recordings made while we were not running.
        for entry in sorted(folder.iterdir()):
            if entry.is_file():
                self.enqueue(entry)

    def _stop_watching(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=5)
            self._observer = None

    # ---- worker -----------------------------------------------------------

    def _worker(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(POLL_SECONDS)
            self._wake.clear()
            if self._stop.is_set():
                break
            ready = self._next_ready()
            if ready and not self._paused and self.encoder:
                try:
                    self._process(ready)
                except Exception:  # never let one bad file kill the worker
                    log.exception("Unexpected error while processing %s", ready)
                self._wake.set()  # look for the next one right away
            self._publish()

    def _next_ready(self) -> Path | None:
        """Update size tracking; return a file that has finished being written."""
        with self._lock:
            items = list(self._pending.items())
        for key, info in items:
            path = Path(key)
            try:
                st = path.stat()
            except OSError:
                with self._lock:
                    self._pending.pop(key, None)  # deleted or renamed
                continue
            if logic.file_key(path, st.st_size, st.st_mtime) in self.skip:
                with self._lock:
                    self._pending.pop(key, None)
                continue
            if st.st_size > 0 and st.st_size == info.size:
                info.stable += 1
            else:
                info.size, info.stable = st.st_size, 0
            if info.stable >= STABLE_CHECKS and fileutil.can_open_exclusively(path):
                with self._lock:
                    self._pending.pop(key, None)
                return path
        return None

    def _process(self, source: Path) -> None:
        st = source.stat()
        key = logic.file_key(source, st.st_size, st.st_mtime)

        src_duration = media.probe_duration(self.ffprobe, source)
        if src_duration is None:
            log.warning("Skipping %s: ffprobe cannot read it", source.name)
            self.skip.add(key)
            return

        self._current = source.name
        self._publish()
        try:
            self._encode_and_verify(source, st, key, src_duration)
        finally:
            self._current = ""

    def _encode_and_verify(self, source: Path, st: os.stat_result, key: str,
                           src_duration: float) -> None:
        settings = self.settings
        partial = logic.partial_path_for(source)
        final = logic.output_path_for(source)
        log.info("Compressing %s (%.1f MB, %.1fs) with %s q=%d",
                 source.name, st.st_size / 1e6, src_duration, self.encoder, settings.quality)
        ok, stderr = media.encode(
            self.ffmpeg, source, partial, self.encoder, settings.quality,
            stop_check=self._stop.is_set,
        )
        if not ok:
            _silent_remove(partial)
            if stderr != "aborted":
                log.error("ffmpeg failed on %s:\n%s", source.name, stderr)
                self.on_notify(f"Failed to compress {source.name}, see log")
            return

        out_size = partial.stat().st_size
        verdict = logic.verify(
            st.st_size, out_size, src_duration, media.probe_duration(self.ffprobe, partial)
        )
        if verdict.action == "replace":
            os.replace(partial, final)
            os.utime(final, (st.st_atime, st.st_mtime))  # keep the recording date
            fileutil.remove(source, permanent=settings.permanent_delete)
            log.info("Done %s -> %s (%.1f MB, %s); original %s",
                     source.name, final.name, out_size / 1e6, verdict.reason,
                     "deleted" if settings.permanent_delete else "moved to Recycle Bin")
        elif verdict.action == "keep_original":
            _silent_remove(partial)
            self.skip.add(key)
            log.info("Kept original %s: %s", source.name, verdict.reason)
        else:
            _silent_remove(partial)
            log.error("Verification failed for %s: %s", source.name, verdict.reason)
            self.on_notify(f"Verification failed for {source.name}: {verdict.reason}")

    # ---- status -----------------------------------------------------------

    def _set_error(self, error: str) -> None:
        self._status = replace(self._status, error=error)
        self._publish()

    def _publish(self) -> None:
        with self._lock:
            queued = len(self._pending)
        current = self._current
        if current:
            state = "compressing"
        elif self._status.error:
            state = "error"
        elif self._paused:
            state = "paused"
        else:
            state = "idle"
        new = Status(state, current, queued, self._status.error, self.encoder)
        if new != self._status:
            self._status = new
            self.on_status(new)


def _silent_remove(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass

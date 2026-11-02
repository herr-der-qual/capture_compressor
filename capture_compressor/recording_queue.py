"""Recordings waiting to be compressed, and detection of when one is finished."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from . import decisions, file_operations
from .skip_list import SkipList

# The size must stay the same for this many checks before we touch a file.
UNCHANGED_SIZE_CHECKS_REQUIRED = 3


@dataclass
class WaitingRecording:
    last_size: int = -1
    unchanged_size_checks: int = 0

    def record_size(self, size: int) -> None:
        if size > 0 and size == self.last_size:
            self.unchanged_size_checks += 1
        else:
            self.last_size = size
            self.unchanged_size_checks = 0

    @property
    def size_is_stable(self) -> bool:
        return self.unchanged_size_checks >= UNCHANGED_SIZE_CHECKS_REQUIRED


class RecordingQueue:
    """Thread safe: the folder watcher adds, the compression worker takes."""

    def __init__(self, skip_list: SkipList) -> None:
        self.skip_list = skip_list
        self._lock = threading.Lock()
        self._waiting: dict[Path, WaitingRecording] = {}

    def add(self, path: Path) -> bool:
        """Returns True if the path was not queued yet."""
        with self._lock:
            if path in self._waiting:
                return False
            self._waiting[path] = WaitingRecording()
            return True

    def clear(self) -> None:
        with self._lock:
            self._waiting.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._waiting)

    def take_finished_recording(self) -> Path | None:
        """Check every waiting file once; remove and return one that is finished."""
        with self._lock:
            waiting = list(self._waiting.items())
        for path, recording in waiting:
            size = self._current_size_unless_forgotten(path)
            if size is None:
                self._remove(path)
            elif self._is_finished(path, recording, size):
                self._remove(path)
                return path
        return None

    def _current_size_unless_forgotten(self, path: Path) -> int | None:
        """None if the file is gone or on the skip list."""
        try:
            file_status = path.stat()
        except OSError:
            return None  # deleted or renamed meanwhile
        identity = decisions.file_version_identity(path, file_status.st_size, file_status.st_mtime)
        return None if identity in self.skip_list else file_status.st_size

    @staticmethod
    def _is_finished(path: Path, recording: WaitingRecording, size: int) -> bool:
        recording.record_size(size)
        return recording.size_is_stable and not file_operations.is_open_by_another_program(path)

    def _remove(self, path: Path) -> None:
        with self._lock:
            self._waiting.pop(path, None)

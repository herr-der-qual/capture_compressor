"""Reports every file that appears or changes in the watch folder."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)
OBSERVER_STOP_TIMEOUT_SECONDS = 5


class _ForwardFileEvents(FileSystemEventHandler):
    def __init__(self, on_file_seen: Callable[[Path], None]) -> None:
        self.on_file_seen = on_file_seen

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.on_file_seen(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.on_file_seen(Path(event.src_path))

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            self.on_file_seen(Path(event.dest_path))


class FolderWatcher:
    def __init__(self, on_file_seen: Callable[[Path], None]) -> None:
        self.on_file_seen = on_file_seen
        self._observer: Observer | None = None

    def start(self, folder: Path) -> None:
        """Watch `folder` (not recursive) and report the files already in it."""
        observer = Observer()
        observer.schedule(_ForwardFileEvents(self.on_file_seen), str(folder), recursive=False)
        observer.start()
        self._observer = observer
        logger.info("Watching %s", folder)
        for existing_file in sorted(folder.iterdir()):
            if existing_file.is_file():
                self.on_file_seen(existing_file)

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=OBSERVER_STOP_TIMEOUT_SECONDS)
            self._observer = None

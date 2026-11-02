"""Log file in the application directory, optionally mirrored to the console."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .settings import application_directory

LOG_FILE_NAME = "capture_compressor.log"
MAXIMUM_LOG_FILE_BYTES = 1_000_000
KEPT_OLD_LOG_FILES = 2


def log_file_path() -> Path:
    return application_directory() / LOG_FILE_NAME


def configure_logging(also_to_console: bool = False) -> Path:
    handlers: list[logging.Handler] = [
        RotatingFileHandler(
            log_file_path(),
            maxBytes=MAXIMUM_LOG_FILE_BYTES,
            backupCount=KEPT_OLD_LOG_FILES,
            encoding="utf-8",
        )
    ]
    if also_to_console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_file_path()

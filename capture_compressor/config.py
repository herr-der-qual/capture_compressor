"""Settings persisted as JSON in %APPDATA%\\CaptureCompressor\\."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from logging.handlers import RotatingFileHandler
from pathlib import Path

from . import logic

APP_NAME = "CaptureCompressor"
log = logging.getLogger(__name__)


def app_dir() -> Path:
    # CAPTURE_COMPRESSOR_HOME lets tests and demos use a throwaway directory.
    override = os.environ.get("CAPTURE_COMPRESSOR_HOME")
    base = Path(override) if override else Path(os.environ["APPDATA"]) / APP_NAME
    base.mkdir(parents=True, exist_ok=True)
    return base


def default_watch_folder() -> str:
    return str(Path(os.environ.get("USERPROFILE", Path.home())) / "Videos" / "Captures")


@dataclass
class Settings:
    watch_folder: str = field(default_factory=default_watch_folder)
    encoder: str = logic.DEFAULT_ENCODER
    quality: int = logic.DEFAULT_QUALITY
    permanent_delete: bool = False
    start_with_windows: bool = True
    ffmpeg_path: str = ""  # empty = use ffmpeg from PATH

    @classmethod
    def load(cls) -> tuple["Settings", bool]:
        """Return (settings, existed). Unknown or broken values fall back to defaults."""
        path = app_dir() / "settings.json"
        if not path.exists():
            return cls(), False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            log.error("Could not read %s, using defaults: %s", path, e)
            return cls(), True
        known = {f.name for f in fields(cls)}
        settings = cls(**{k: v for k, v in data.items() if k in known})
        if settings.encoder not in logic.ENCODERS:
            settings.encoder = logic.DEFAULT_ENCODER
        return settings, True

    def save(self) -> None:
        path = app_dir() / "settings.json"
        path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


class SkipList:
    """Files that did not get smaller; remembered so we don't retry them forever."""

    def __init__(self) -> None:
        self.path = app_dir() / "skipped.json"
        try:
            self.keys: set[str] = set(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            self.keys = set()

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def add(self, key: str) -> None:
        self.keys.add(key)
        self.path.write_text(json.dumps(sorted(self.keys), indent=2), encoding="utf-8")


def setup_logging(also_console: bool = False) -> Path:
    log_path = app_dir() / "capture_compressor.log"
    handlers: list[logging.Handler] = [
        RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    ]
    if also_console:
        handlers.append(logging.StreamHandler())
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )
    return log_path

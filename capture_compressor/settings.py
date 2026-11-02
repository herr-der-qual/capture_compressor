"""User settings, persisted as JSON in %APPDATA%\\CaptureCompressor\\."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path

from . import decisions

APPLICATION_NAME = "CaptureCompressor"
SETTINGS_FILE_NAME = "settings.json"
# Lets tests and demos use a throwaway directory instead of %APPDATA%.
HOME_OVERRIDE_VARIABLE = "CAPTURE_COMPRESSOR_HOME"

logger = logging.getLogger(__name__)


def application_directory() -> Path:
    override = os.environ.get(HOME_OVERRIDE_VARIABLE)
    directory = Path(override) if override else Path(os.environ["APPDATA"]) / APPLICATION_NAME
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def default_watch_folder() -> str:
    user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
    return str(user_profile / "Videos" / "Captures")


@dataclass
class Settings:
    watch_folder: str = field(default_factory=default_watch_folder)
    encoder: str = decisions.DEFAULT_ENCODER
    quality: int = decisions.DEFAULT_QUALITY
    permanent_delete: bool = False
    start_with_windows: bool = True
    ffmpeg_path: str = ""  # empty means ffmpeg from PATH

    @classmethod
    def load(cls) -> tuple["Settings", bool]:
        """Return (settings, file_existed). Unknown or broken values fall back to defaults."""
        settings_file = application_directory() / SETTINGS_FILE_NAME
        if not settings_file.exists():
            return cls(), False
        try:
            stored_values = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            logger.error("Could not read %s, using defaults: %s", settings_file, error)
            return cls(), True
        return cls._from_stored_values(stored_values), True

    @classmethod
    def _from_stored_values(cls, stored_values: dict) -> "Settings":
        known_names = {setting.name for setting in fields(cls)}
        settings = cls(**{name: value for name, value in stored_values.items() if name in known_names})
        if settings.encoder not in decisions.ENCODER_DESCRIPTIONS:
            settings.encoder = decisions.DEFAULT_ENCODER
        return settings

    def save(self) -> None:
        settings_file = application_directory() / SETTINGS_FILE_NAME
        settings_file.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")

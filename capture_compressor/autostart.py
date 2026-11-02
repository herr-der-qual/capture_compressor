"""Start with Windows via the per-user Run registry key (no administrator rights needed)."""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CaptureCompressor"
LAUNCHER_FILE_NAME = "capture_compressor.pyw"

logger = logging.getLogger(__name__)


def startup_command() -> str:
    """The command line Windows should run at logon."""
    if getattr(sys, "frozen", False):  # PyInstaller executable
        return f'"{sys.executable}"'
    python = Path(sys.executable)
    windowless_python = python.with_name("pythonw.exe")
    launcher = Path(__file__).resolve().parent.parent / LAUNCHER_FILE_NAME
    interpreter = windowless_python if windowless_python.exists() else python
    return f'"{interpreter}" "{launcher}"'


def registered_command(value_name: str = VALUE_NAME) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as run_key:
            return winreg.QueryValueEx(run_key, value_name)[0]
    except FileNotFoundError:
        return None


def set_enabled(enabled: bool, value_name: str = VALUE_NAME) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as run_key:
        if enabled:
            winreg.SetValueEx(run_key, value_name, 0, winreg.REG_SZ, startup_command())
            return
        try:
            winreg.DeleteValue(run_key, value_name)
        except FileNotFoundError:
            pass


def synchronize(enabled: bool) -> None:
    """Make the registry match the setting (this also fixes a moved checkout)."""
    wanted_command = startup_command() if enabled else None
    if registered_command() != wanted_command:
        set_enabled(enabled)
        logger.info("Start with Windows %s", "enabled" if enabled else "disabled")

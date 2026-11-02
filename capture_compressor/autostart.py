"""Start with Windows via the per-user Run key (no admin rights needed)."""

from __future__ import annotations

import logging
import sys
import winreg
from pathlib import Path

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "CaptureCompressor"
log = logging.getLogger(__name__)


def command() -> str:
    """The command line Windows should run at logon."""
    if getattr(sys, "frozen", False):  # PyInstaller exe
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    launcher = Path(__file__).resolve().parent.parent / "capture_compressor.pyw"
    return f'"{pythonw if pythonw.exists() else exe}" "{launcher}"'


def current(value_name: str = VALUE_NAME) -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            return winreg.QueryValueEx(key, value_name)[0]
    except FileNotFoundError:
        return None


def set_enabled(enabled: bool, value_name: str = VALUE_NAME) -> None:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, command())
        else:
            try:
                winreg.DeleteValue(key, value_name)
            except FileNotFoundError:
                pass


def sync(enabled: bool) -> None:
    """Make the registry match the setting (also fixes a moved checkout)."""
    want = command() if enabled else None
    if current() != want:
        set_enabled(enabled)
        log.info("Start with Windows %s", "enabled" if enabled else "disabled")

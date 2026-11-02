"""Makes sure only one copy of the application runs per user session."""

from __future__ import annotations

import ctypes

MUTEX_NAME = "Local\\CaptureCompressorSingleInstance"
ERROR_ALREADY_EXISTS = 183

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)


def another_instance_is_running() -> bool:
    """Creates a named mutex; Windows keeps it until this process exits."""
    _kernel32.CreateMutexW(None, False, MUTEX_NAME)
    return ctypes.get_last_error() == ERROR_ALREADY_EXISTS

"""Windows file helpers: exclusive-open check and deletion."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from send2trash import send2trash

_GENERIC_READ = 0x80000000
_OPEN_EXISTING = 3
_FILE_ATTRIBUTE_NORMAL = 0x80
_INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_kernel32.CreateFileW.restype = wintypes.HANDLE
_kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
_kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def can_open_exclusively(path: Path) -> bool:
    """True if no other process has the file open (share mode 0 succeeds).

    Python's open() always allows sharing, so it can't tell whether Game Bar
    is still writing; CreateFileW with dwShareMode=0 can.
    """
    handle = _kernel32.CreateFileW(
        str(path), _GENERIC_READ, 0, None, _OPEN_EXISTING, _FILE_ATTRIBUTE_NORMAL, None
    )
    if handle == _INVALID_HANDLE_VALUE:
        return False
    _kernel32.CloseHandle(handle)
    return True


def remove(path: Path, permanent: bool) -> None:
    if permanent:
        os.remove(path)
    else:
        send2trash(str(path))

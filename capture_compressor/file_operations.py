"""Windows file helpers: checking that nobody else has a file open, and deleting files."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path

from send2trash import send2trash

# Win32 constants, named as in the Windows API documentation.
GENERIC_READ = 0x80000000
NO_SHARING = 0
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x80
INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.CreateFileW.restype = wintypes.HANDLE
kernel32.CreateFileW.argtypes = [
    wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
    wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE,
]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def is_open_by_another_program(path: Path) -> bool:
    """True while another process (for example Game Bar recording) holds the file open.

    Python's open() always allows sharing, so it cannot tell. Opening with
    share mode 0 fails as long as anyone else has a handle.
    """
    handle = kernel32.CreateFileW(
        str(path), GENERIC_READ, NO_SHARING, None, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, None
    )
    if handle == INVALID_HANDLE_VALUE:
        return True
    kernel32.CloseHandle(handle)
    return False


def delete_file(path: Path, permanently: bool) -> None:
    """Delete permanently or move to the Recycle Bin."""
    if permanently:
        os.remove(path)
    else:
        send2trash(str(path))


def delete_if_exists(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass

"""Builds dist\\CaptureCompressor.exe, a single file that runs without Python installed.

Usage: .venv\\Scripts\\python build_executable.py
ffmpeg is not bundled; it still has to be on PATH or set in Settings.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from capture_compressor import __version__, status
from capture_compressor.tray_icon_image import draw_tray_icon

PROJECT_DIRECTORY = Path(__file__).resolve().parent
BUILD_DIRECTORY = PROJECT_DIRECTORY / "build"
DISTRIBUTION_DIRECTORY = PROJECT_DIRECTORY / "dist"
EXECUTABLE_NAME = "CaptureCompressor"
ICON_SIZES = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64)]
# Both libraries pick their Windows backend at run time, so PyInstaller can't see the import.
HIDDEN_IMPORTS = ["pystray._win32", "watchdog.observers.read_directory_changes"]


def write_icon_file() -> Path:
    icon_file = BUILD_DIRECTORY / "capture_compressor.ico"
    BUILD_DIRECTORY.mkdir(exist_ok=True)
    draw_tray_icon(status.IDLE).save(icon_file, sizes=ICON_SIZES)
    return icon_file


def build() -> Path:
    icon_file = write_icon_file()
    arguments = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean",
        "--onefile",
        "--windowed",  # no console window, like pythonw
        "--name", EXECUTABLE_NAME,
        "--icon", str(icon_file),
        "--distpath", str(DISTRIBUTION_DIRECTORY),
        "--workpath", str(BUILD_DIRECTORY / "work"),
        "--specpath", str(BUILD_DIRECTORY),
        *[argument for module in HIDDEN_IMPORTS for argument in ("--hidden-import", module)],
        str(PROJECT_DIRECTORY / "capture_compressor.pyw"),
    ]
    subprocess.run(arguments, check=True, cwd=PROJECT_DIRECTORY)
    return DISTRIBUTION_DIRECTORY / f"{EXECUTABLE_NAME}.exe"


if __name__ == "__main__":
    executable = build()
    size_in_megabytes = executable.stat().st_size / 1_000_000
    print(f"Built {executable} ({size_in_megabytes:.1f} MB), version {__version__}")

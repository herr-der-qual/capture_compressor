"""Finding and running ffmpeg and ffprobe."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Callable

from . import decisions

logger = logging.getLogger(__name__)

# Without this flag every ffmpeg call flashes a console window under pythonw.
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROBE_TIMEOUT_SECONDS = 60
ENCODER_TEST_TIMEOUT_SECONDS = 60
KEPT_ERROR_OUTPUT_LINES = 20
ABORTED = "aborted"


class FfmpegNotFound(RuntimeError):
    pass


def find_ffmpeg_and_ffprobe(configured_path: str = "") -> tuple[str, str]:
    """`configured_path` may be ffmpeg.exe or its folder; empty means search PATH."""
    if configured_path:
        return _find_in_folder(Path(configured_path))
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FfmpegNotFound("ffmpeg / ffprobe not found on PATH")
    return ffmpeg, ffprobe


def _find_in_folder(configured_path: Path) -> tuple[str, str]:
    folder = configured_path if configured_path.is_dir() else configured_path.parent
    ffmpeg, ffprobe = folder / "ffmpeg.exe", folder / "ffprobe.exe"
    if not (ffmpeg.exists() and ffprobe.exists()):
        raise FfmpegNotFound(f"ffmpeg.exe / ffprobe.exe not found in {folder}")
    return str(ffmpeg), str(ffprobe)


def _run_hidden(arguments: list[str], timeout_seconds: float) -> subprocess.CompletedProcess:
    return subprocess.run(
        arguments,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        creationflags=CREATE_NO_WINDOW,
    )


def probe_duration(ffprobe: str, video: Path) -> float | None:
    """Duration in seconds, or None if ffprobe cannot read the file."""
    arguments = [
        ffprobe, "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", str(video),
    ]
    try:
        result = _run_hidden(arguments, PROBE_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        logger.warning("ffprobe failed on %s: %s", video, error)
        return None
    if result.returncode != 0:
        logger.warning("ffprobe failed on %s: %s", video, result.stderr.strip())
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def test_encoder(ffmpeg: str, encoder: str) -> str | None:
    """Encode a one-second test clip. Returns None if it works, otherwise the reason."""
    arguments = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30", "-t", "1",
        "-c:v", encoder, "-f", "null", "-",
    ]
    try:
        result = _run_hidden(arguments, ENCODER_TEST_TIMEOUT_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        return str(error)
    if result.returncode == 0:
        return None
    return _first_error_lines(result.stderr) or f"exit code {result.returncode}"


def _first_error_lines(error_output: str, count: int = 2) -> str:
    """The first lines carry the real reason (for example "driver too old")."""
    lines = [line for line in error_output.splitlines() if line.strip()]
    # Drop the "[hevc_nvenc @ 0000...] " prefix ffmpeg puts in front of each message.
    return " / ".join(line.split("] ", 1)[-1] for line in lines[:count])


def encode(
    ffmpeg: str,
    source: Path,
    target: Path,
    encoder: str,
    quality: int,
    should_abort: Callable[[], bool] = lambda: False,
) -> tuple[bool, str]:
    """Run the encode. Returns (succeeded, last lines of ffmpeg output)."""
    arguments = decisions.build_ffmpeg_arguments(ffmpeg, source, target, encoder, quality)
    logger.info("Running: %s", subprocess.list2cmdline(arguments))
    process = subprocess.Popen(
        arguments,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    last_lines: list[str] = []
    for line in process.stderr:
        last_lines = (last_lines + [line.rstrip()])[-KEPT_ERROR_OUTPUT_LINES:]
        if should_abort():
            process.kill()
            process.wait()
            return False, ABORTED
    process.wait()
    return process.returncode == 0, "\n".join(last_lines)

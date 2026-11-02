"""Running ffmpeg / ffprobe."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from . import logic

log = logging.getLogger(__name__)

# No console window flashing up when running under pythonw.
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FfmpegNotFound(RuntimeError):
    pass


def resolve_tools(ffmpeg_path: str = "") -> tuple[str, str]:
    """Return (ffmpeg, ffprobe). `ffmpeg_path` may be ffmpeg.exe or its folder."""
    if ffmpeg_path:
        p = Path(ffmpeg_path)
        folder = p if p.is_dir() else p.parent
        ffmpeg, ffprobe = folder / "ffmpeg.exe", folder / "ffprobe.exe"
        if ffmpeg.exists() and ffprobe.exists():
            return str(ffmpeg), str(ffprobe)
        raise FfmpegNotFound(f"ffmpeg.exe / ffprobe.exe not found in {folder}")
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        raise FfmpegNotFound("ffmpeg / ffprobe not found on PATH")
    return ffmpeg, ffprobe


def _run(args: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        creationflags=NO_WINDOW,
    )


def probe_duration(ffprobe: str, path: Path) -> float | None:
    try:
        r = _run(
            [ffprobe, "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        log.warning("ffprobe failed on %s: %s", path, e)
        return None
    if r.returncode != 0:
        log.warning("ffprobe failed on %s: %s", path, r.stderr.strip())
        return None
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


def test_encoder(ffmpeg: str, encoder: str) -> str | None:
    """Encode a tiny test clip. Returns None if OK, otherwise a short error text."""
    args = [
        ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc=size=640x360:rate=30", "-t", "1",
        "-c:v", encoder, "-f", "null", "-",
    ]
    try:
        r = _run(args, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    if r.returncode == 0:
        return None
    lines = [l for l in r.stderr.splitlines() if l.strip()]
    # The first lines usually carry the real reason (e.g. driver too old).
    return " / ".join(l.split("] ", 1)[-1] for l in lines[:2]) or f"exit code {r.returncode}"


def encode(
    ffmpeg: str, source: Path, target: Path, encoder: str, quality: int,
    stop_check=None,
) -> tuple[bool, str]:
    """Run the encode. Returns (ok, stderr tail). `stop_check()` -> True aborts."""
    args = logic.build_ffmpeg_args(ffmpeg, source, target, encoder, quality)
    log.info("Running: %s", subprocess.list2cmdline(args))
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=NO_WINDOW,
    )
    tail: list[str] = []
    assert proc.stderr is not None
    for line in proc.stderr:
        tail = (tail + [line.rstrip()])[-20:]
        if stop_check and stop_check():
            proc.kill()
            proc.wait()
            return False, "aborted"
    proc.wait()
    return proc.returncode == 0, "\n".join(tail)

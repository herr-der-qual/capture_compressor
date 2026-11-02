"""Pure decision logic: naming, skip rules, ffmpeg arguments and verification.

Nothing in this module touches the file system or runs processes, so it is
easy to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COMPRESSED_MARKER = ".compressed"
PARTIAL_MARKER = ".partial"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}

ENCODERS = {
    "hevc_nvenc": "GPU - NVIDIA HEVC (hevc_nvenc)",
    "libx265": "CPU - HEVC (libx265)",
    "libx264": "CPU - H.264 (libx264)",
}
DEFAULT_ENCODER = "hevc_nvenc"
FALLBACK_ENCODER = "libx265"
DEFAULT_QUALITY = 28  # CRF / CQ: lower = better quality, bigger file
QUALITY_RANGE = (0, 51)


def output_path_for(source: Path) -> Path:
    """`Clip.mp4` -> `Clip.compressed.mp4` (next to the original)."""
    return source.with_name(f"{source.stem}{COMPRESSED_MARKER}{source.suffix}")


def partial_path_for(source: Path) -> Path:
    """Temporary file ffmpeg writes to: `Clip.compressed.partial.mp4`."""
    return source.with_name(
        f"{source.stem}{COMPRESSED_MARKER}{PARTIAL_MARKER}{source.suffix}"
    )


def is_candidate(path: Path) -> bool:
    """True if the file looks like an uncompressed recording we should handle."""
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        return False
    # Never re-compress our own output (or its temporary file).
    if COMPRESSED_MARKER in path.stem.lower():
        return False
    if path.name.startswith(("~", ".")):
        return False
    return True


def build_ffmpeg_args(
    ffmpeg: str, source: Path, target: Path, encoder: str, quality: int
) -> list[str]:
    """Re-encode video only; keep resolution, frame timing and audio as is."""
    quality = max(QUALITY_RANGE[0], min(QUALITY_RANGE[1], int(quality)))
    args = [
        ffmpeg, "-hide_banner", "-nostdin", "-y",
        "-i", str(source),
        "-map", "0:v", "-map", "0:a?",
        "-c:v", encoder,
    ]
    if encoder.endswith("_nvenc"):
        args += ["-preset", "p5", "-rc", "vbr", "-cq", str(quality), "-b:v", "0"]
    else:
        args += ["-preset", "medium", "-crf", str(quality)]
    if encoder in ("hevc_nvenc", "libx265"):
        args += ["-tag:v", "hvc1"]  # lets Windows / QuickTime players open HEVC mp4
    if encoder == "libx265":
        args += ["-x265-params", "log-level=error"]
    args += [
        "-fps_mode", "passthrough",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(target),
    ]
    return args


@dataclass(frozen=True)
class Verdict:
    action: str  # "replace" | "keep_original" | "failed"
    reason: str

    @property
    def delete_original(self) -> bool:
        return self.action == "replace"


def duration_tolerance(duration: float) -> float:
    return max(0.5, duration * 0.01)


def verify(
    source_size: int,
    output_size: int,
    source_duration: float | None,
    output_duration: float | None,
) -> Verdict:
    """Decide what to do after an encode finished."""
    if output_duration is None or output_size <= 0:
        return Verdict("failed", "output could not be read by ffprobe")
    if source_duration is None:
        return Verdict("failed", "original duration unknown")
    diff = abs(source_duration - output_duration)
    if diff > duration_tolerance(source_duration):
        return Verdict(
            "failed",
            f"duration mismatch: {source_duration:.2f}s vs {output_duration:.2f}s",
        )
    if output_size >= source_size:
        return Verdict(
            "keep_original",
            f"output not smaller ({output_size} >= {source_size} bytes)",
        )
    saved = 100 * (1 - output_size / source_size)
    return Verdict("replace", f"saved {saved:.0f}%")


def file_key(path: Path, size: int, mtime: float) -> str:
    """Identity of a file version, used to remember files we gave up on."""
    return f"{str(path).lower()}|{size}|{int(mtime)}"

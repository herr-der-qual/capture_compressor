"""Pure decisions: output naming, which files to handle, ffmpeg arguments, verification.

Nothing here touches the file system or starts processes, so it is easy to test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

COMPRESSED_MARKER = ".compressed"
PARTIAL_MARKER = ".partial"
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm"}
IGNORED_NAME_PREFIXES = ("~", ".")

ENCODER_DESCRIPTIONS = {
    "libx264": "CPU - H.264 (libx264), plays everywhere",
    "libx265": "CPU - HEVC (libx265), smaller, needs HEVC codec",
    "hevc_nvenc": "GPU - NVIDIA HEVC (hevc_nvenc), needs HEVC codec",
}
HEVC_ENCODERS = {"hevc_nvenc", "libx265"}
# H.264 by default: Windows' own player needs a paid extension to open HEVC files.
DEFAULT_ENCODER = "libx264"
FALLBACK_ENCODER = "libx264"

DEFAULT_QUALITY = 23  # CRF / CQ: lower means better quality and bigger files; x264's own default
LOWEST_QUALITY_VALUE = 0
HIGHEST_QUALITY_VALUE = 51

MINIMUM_DURATION_TOLERANCE_SECONDS = 0.5
RELATIVE_DURATION_TOLERANCE = 0.01


def compressed_path_for(source: Path) -> Path:
    """`Clip.mp4` -> `Clip.compressed.mp4`, next to the original."""
    return source.with_name(f"{source.stem}{COMPRESSED_MARKER}{source.suffix}")


def partial_path_for(source: Path) -> Path:
    """Temporary file ffmpeg writes to: `Clip.compressed.partial.mp4`."""
    return source.with_name(
        f"{source.stem}{COMPRESSED_MARKER}{PARTIAL_MARKER}{source.suffix}"
    )


def is_uncompressed_recording(path: Path) -> bool:
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        return False
    if path.name.startswith(IGNORED_NAME_PREFIXES):
        return False
    # Never compress our own output (or its temporary file) again.
    return COMPRESSED_MARKER not in path.stem.lower()


def clamp_quality(quality: int) -> int:
    return max(LOWEST_QUALITY_VALUE, min(HIGHEST_QUALITY_VALUE, int(quality)))


def build_ffmpeg_arguments(
    ffmpeg: str, source: Path, target: Path, encoder: str, quality: int
) -> list[str]:
    """Re-encode the video only; keep resolution, frame timing and audio unchanged."""
    return [
        ffmpeg, "-hide_banner", "-nostdin", "-y",
        "-i", str(source),
        "-map", "0:v", "-map", "0:a?",
        "-c:v", encoder,
        *_encoder_quality_arguments(encoder, clamp_quality(quality)),
        *_encoder_specific_arguments(encoder),
        "-fps_mode", "passthrough",
        "-c:a", "copy",
        "-movflags", "+faststart",
        str(target),
    ]


def _encoder_quality_arguments(encoder: str, quality: int) -> list[str]:
    if encoder.endswith("_nvenc"):
        return ["-preset", "p5", "-rc", "vbr", "-cq", str(quality), "-b:v", "0"]
    return ["-preset", "medium", "-crf", str(quality)]


def _encoder_specific_arguments(encoder: str) -> list[str]:
    arguments = []
    if encoder in HEVC_ENCODERS:
        arguments += ["-tag:v", "hvc1"]  # lets Windows and QuickTime players open HEVC mp4
    if encoder == "libx265":
        arguments += ["-x265-params", "log-level=error"]
    return arguments


@dataclass(frozen=True)
class Verdict:
    action: str  # "replace" | "keep_original" | "failed"
    reason: str

    @property
    def delete_original(self) -> bool:
        return self.action == "replace"


def duration_tolerance(duration_seconds: float) -> float:
    return max(MINIMUM_DURATION_TOLERANCE_SECONDS, duration_seconds * RELATIVE_DURATION_TOLERANCE)


def verify_compression(
    source_size: int,
    output_size: int,
    source_duration: float | None,
    output_duration: float | None,
) -> Verdict:
    """Decide what to do with an encode that has just finished."""
    if output_duration is None or output_size <= 0:
        return Verdict("failed", "output could not be read by ffprobe")
    if source_duration is None:
        return Verdict("failed", "original duration unknown")
    if abs(source_duration - output_duration) > duration_tolerance(source_duration):
        return Verdict(
            "failed",
            f"duration mismatch: {source_duration:.2f}s vs {output_duration:.2f}s",
        )
    if output_size >= source_size:
        return Verdict(
            "keep_original",
            f"output not smaller ({output_size} >= {source_size} bytes)",
        )
    saved_percent = 100 * (1 - output_size / source_size)
    return Verdict("replace", f"saved {saved_percent:.0f}%")


def file_version_identity(path: Path, size: int, modification_time: float) -> str:
    """Identifies one version of a file; used to remember files we gave up on."""
    return f"{str(path).lower()}|{size}|{int(modification_time)}"

from pathlib import Path

import pytest

from capture_compressor import decisions


def test_compressed_name_inserts_marker_before_extension():
    assert decisions.compressed_path_for(Path(r"C:\v\Clip.mp4")) == Path(r"C:\v\Clip.compressed.mp4")
    assert decisions.compressed_path_for(Path(r"C:\v\a.b.mkv")) == Path(r"C:\v\a.b.compressed.mkv")


def test_partial_file_is_never_treated_as_a_recording():
    partial = decisions.partial_path_for(Path(r"C:\v\Clip.mp4"))
    assert partial == Path(r"C:\v\Clip.compressed.partial.mp4")
    assert not decisions.is_uncompressed_recording(partial)


@pytest.mark.parametrize("name", [
    "Game 2026-11-02 13-00-00.mp4", "clip.MKV", "x.mov", "y.webm",
])
def test_recordings_are_accepted(name):
    assert decisions.is_uncompressed_recording(Path(name))


@pytest.mark.parametrize("name", [
    "Clip.compressed.mp4", "Clip.COMPRESSED.mp4", "Clip.compressed.partial.mp4",
    "shot.png", "notes.txt", "~temporary.mp4", ".hidden.mp4", "no_extension",
])
def test_other_files_are_ignored(name):
    assert not decisions.is_uncompressed_recording(Path(name))


def test_output_of_any_recording_is_ignored():
    for name in ["a.mp4", "b.c.mkv"]:
        assert not decisions.is_uncompressed_recording(decisions.compressed_path_for(Path(name)))


def test_replace_when_smaller_and_same_duration():
    verdict = decisions.verify_compression(1000, 400, 60.0, 60.2)
    assert verdict.action == "replace" and verdict.delete_original
    assert "60%" in verdict.reason


def test_keep_original_when_output_is_not_smaller():
    assert decisions.verify_compression(1000, 1000, 10.0, 10.0).action == "keep_original"
    bigger = decisions.verify_compression(1000, 1200, 10.0, 10.0)
    assert bigger.action == "keep_original" and not bigger.delete_original


@pytest.mark.parametrize("source_duration,output_duration", [(60.0, 58.0), (10.0, 9.0), (600.0, 590.0)])
def test_fail_on_duration_mismatch(source_duration, output_duration):
    verdict = decisions.verify_compression(1000, 10, source_duration, output_duration)
    assert verdict.action == "failed" and not verdict.delete_original


def test_duration_tolerance_scales_with_length():
    assert decisions.verify_compression(1000, 10, 600.0, 595.0).action == "replace"  # 1% of 10 minutes = 6 s
    assert decisions.verify_compression(1000, 10, 5.0, 5.4).action == "replace"      # minimum 0.5 s


def test_fail_when_output_cannot_be_read():
    assert decisions.verify_compression(1000, 10, 10.0, None).action == "failed"
    assert decisions.verify_compression(1000, 0, 10.0, 10.0).action == "failed"
    assert decisions.verify_compression(1000, 10, None, 10.0).action == "failed"


def test_ffmpeg_arguments_for_gpu():
    arguments = decisions.build_ffmpeg_arguments("ffmpeg", Path("in.mp4"), Path("out.mp4"), "hevc_nvenc", 30)
    assert arguments[arguments.index("-c:v") + 1] == "hevc_nvenc"
    assert arguments[arguments.index("-cq") + 1] == "30"
    assert "-crf" not in arguments
    assert arguments[arguments.index("-c:a") + 1] == "copy"
    assert "-vf" not in arguments and "-r" not in arguments  # resolution and frame rate untouched
    assert arguments[-1] == "out.mp4"


@pytest.mark.parametrize("encoder", ["libx265", "libx264"])
def test_ffmpeg_arguments_for_cpu(encoder):
    arguments = decisions.build_ffmpeg_arguments("ffmpeg", Path("in.mp4"), Path("out.mp4"), encoder, 23)
    assert arguments[arguments.index("-crf") + 1] == "23"
    assert ("-tag:v" in arguments) == (encoder == "libx265")


def test_quality_is_clamped():
    arguments = decisions.build_ffmpeg_arguments("ffmpeg", Path("i.mp4"), Path("o.mp4"), "libx264", 99)
    assert arguments[arguments.index("-crf") + 1] == "51"


def test_file_version_identity_changes_when_file_changes():
    path = Path(r"C:\v\Clip.mp4")
    assert decisions.file_version_identity(path, 1, 2.0) == decisions.file_version_identity(Path(r"c:\V\clip.MP4"), 1, 2.9)
    assert decisions.file_version_identity(path, 1, 2.0) != decisions.file_version_identity(path, 2, 2.0)

from pathlib import Path

import pytest

from capture_compressor import logic


def test_output_name_inserts_marker_before_extension():
    assert logic.output_path_for(Path(r"C:\v\Clip.mp4")) == Path(r"C:\v\Clip.compressed.mp4")
    assert logic.output_path_for(Path(r"C:\v\a.b.mkv")) == Path(r"C:\v\a.b.compressed.mkv")


def test_partial_name_is_itself_never_a_candidate():
    partial = logic.partial_path_for(Path(r"C:\v\Clip.mp4"))
    assert partial == Path(r"C:\v\Clip.compressed.partial.mp4")
    assert not logic.is_candidate(partial)


@pytest.mark.parametrize("name", [
    "Game 2026-11-02 13-00-00.mp4", "clip.MKV", "x.mov", "y.webm",
])
def test_candidates(name):
    assert logic.is_candidate(Path(name))


@pytest.mark.parametrize("name", [
    "Clip.compressed.mp4", "Clip.COMPRESSED.mp4", "Clip.compressed.partial.mp4",
    "shot.png", "notes.txt", "~tmp.mp4", ".hidden.mp4", "noext",
])
def test_not_candidates(name):
    assert not logic.is_candidate(Path(name))


def test_output_of_any_candidate_is_skipped():
    for name in ["a.mp4", "b.c.mkv"]:
        assert not logic.is_candidate(logic.output_path_for(Path(name)))


def test_verify_replace_when_smaller_and_same_duration():
    v = logic.verify(1000, 400, 60.0, 60.2)
    assert v.action == "replace" and v.delete_original
    assert "60%" in v.reason


def test_verify_keeps_original_when_not_smaller():
    assert logic.verify(1000, 1000, 10.0, 10.0).action == "keep_original"
    assert logic.verify(1000, 1200, 10.0, 10.0).action == "keep_original"
    assert not logic.verify(1000, 1200, 10.0, 10.0).delete_original


@pytest.mark.parametrize("src,out", [(60.0, 58.0), (10.0, 9.0), (600.0, 590.0)])
def test_verify_fails_on_duration_mismatch(src, out):
    v = logic.verify(1000, 10, src, out)
    assert v.action == "failed" and not v.delete_original


def test_verify_tolerance_scales_with_length():
    assert logic.verify(1000, 10, 600.0, 595.0).action == "replace"  # 1% of 10 min = 6 s
    assert logic.verify(1000, 10, 5.0, 5.4).action == "replace"      # minimum 0.5 s


def test_verify_fails_when_output_unreadable():
    assert logic.verify(1000, 10, 10.0, None).action == "failed"
    assert logic.verify(1000, 0, 10.0, 10.0).action == "failed"
    assert logic.verify(1000, 10, None, 10.0).action == "failed"


def test_ffmpeg_args_gpu():
    args = logic.build_ffmpeg_args("ffmpeg", Path("in.mp4"), Path("out.mp4"), "hevc_nvenc", 30)
    assert args[args.index("-c:v") + 1] == "hevc_nvenc"
    assert args[args.index("-cq") + 1] == "30"
    assert "-crf" not in args
    assert args[args.index("-c:a") + 1] == "copy"
    assert "-vf" not in args and "-r" not in args  # resolution and fps untouched
    assert args[-1] == "out.mp4"


@pytest.mark.parametrize("encoder", ["libx265", "libx264"])
def test_ffmpeg_args_cpu(encoder):
    args = logic.build_ffmpeg_args("ffmpeg", Path("in.mp4"), Path("out.mp4"), encoder, 23)
    assert args[args.index("-crf") + 1] == "23"
    assert ("-tag:v" in args) == (encoder == "libx265")


def test_ffmpeg_args_quality_is_clamped():
    args = logic.build_ffmpeg_args("ffmpeg", Path("i.mp4"), Path("o.mp4"), "libx264", 99)
    assert args[args.index("-crf") + 1] == "51"


def test_file_key_changes_when_file_changes():
    p = Path(r"C:\v\Clip.mp4")
    assert logic.file_key(p, 1, 2.0) == logic.file_key(Path(r"c:\V\clip.MP4"), 1, 2.9)
    assert logic.file_key(p, 1, 2.0) != logic.file_key(p, 2, 2.0)

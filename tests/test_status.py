from capture_compressor import status
from capture_compressor.status import Status


def test_compressing_wins_over_error_and_pause():
    assert status.decide_state("Clip.mp4", "boom", paused=True) == status.COMPRESSING


def test_error_wins_over_pause():
    assert status.decide_state("", "boom", paused=True) == status.ERROR


def test_paused_and_idle():
    assert status.decide_state("", "", paused=True) == status.PAUSED
    assert status.decide_state("", "", paused=False) == status.IDLE


def test_description_shows_queue_length():
    assert Status(status.COMPRESSING, "Clip.mp4", 2).describe() == "Compressing Clip.mp4 - 2 queued"
    assert Status(status.IDLE).describe() == "Idle"
    assert Status(status.ERROR, error="ffmpeg not found").describe() == "Error: ffmpeg not found"

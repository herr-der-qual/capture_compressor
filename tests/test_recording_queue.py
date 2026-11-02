from capture_compressor.recording_queue import UNCHANGED_SIZE_CHECKS_REQUIRED, WaitingRecording


def test_size_must_stay_unchanged_for_several_checks():
    recording = WaitingRecording()
    for _ in range(UNCHANGED_SIZE_CHECKS_REQUIRED):
        recording.record_size(100)
        assert not recording.size_is_stable
    recording.record_size(100)
    assert recording.size_is_stable


def test_growing_file_is_not_stable():
    recording = WaitingRecording()
    for size in range(1, 10):
        recording.record_size(size * 100)
    assert not recording.size_is_stable


def test_empty_file_is_never_stable():
    recording = WaitingRecording()
    for _ in range(10):
        recording.record_size(0)
    assert not recording.size_is_stable

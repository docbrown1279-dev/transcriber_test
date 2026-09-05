"""Tests for VAD region pre-merge before diarization windows."""

from transcriber.diarization.regions import Interval, merge_speech_regions


def test_merge_speech_regions_gap() -> None:
    regions = [
        Interval(0.0, 1.0),
        Interval(1.2, 2.0),  # gap 0.2 <= 0.3 → merge
        Interval(3.0, 4.0),  # gap 1.0 → new island
    ]
    merged = merge_speech_regions(regions, max_gap_sec=0.3, min_duration_sec=0.0)
    assert len(merged) == 2
    assert merged[0].start == 0.0 and merged[0].end == 2.0
    assert merged[1].start == 3.0 and merged[1].end == 4.0


def test_merge_speech_regions_min_duration() -> None:
    regions = [
        Interval(0.0, 0.3),
        Interval(1.0, 2.5),
    ]
    merged = merge_speech_regions(regions, max_gap_sec=0.3, min_duration_sec=0.4)
    assert len(merged) == 1
    assert merged[0].start == 1.0

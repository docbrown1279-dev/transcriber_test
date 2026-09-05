"""Тесты поиска пауз (holes detection)."""

from transcriber.asr.holes import find_holes
from transcriber.models.artifacts import TimeInterval


def test_d1_hol_01_gaps_at_or_above_min_hole_sec_listed() -> None:
    """[D1-HOL-01] gaps >= min_hole_sec listed; shorter gaps ignored."""
    intervals = [
        TimeInterval(start=1.0, end=3.0),
        TimeInterval(start=3.2, end=5.0),  # gap = 0.2s (< 0.5s) -> ignored
        TimeInterval(start=6.0, end=8.0),  # gap = 1.0s (>= 0.5s) -> listed
    ]
    # При total_duration_sec=10.0:
    # Пауза в начале: [0.0, 1.0] (длина 1.0 >= 0.5) -> listed
    # Пауза между [3.0, 3.2] (длина 0.2 < 0.5) -> ignored
    # Пауза между [5.0, 6.0] (длина 1.0 >= 0.5) -> listed
    # Пауза в конце: [8.0, 10.0] (длина 2.0 >= 0.5) -> listed
    holes = find_holes(intervals, total_duration_sec=10.0, min_hole_sec=0.5)

    assert len(holes) == 3
    assert holes[0].start == 0.0
    assert holes[0].end == 1.0

    assert holes[1].start == 5.0
    assert holes[1].end == 6.0

    assert holes[2].start == 8.0
    assert holes[2].end == 10.0

    # Проверка, когда интервалов нет вообще
    empty_holes = find_holes([], total_duration_sec=5.0, min_hole_sec=0.5)
    assert len(empty_holes) == 1
    assert empty_holes[0].start == 0.0
    assert empty_holes[0].end == 5.0

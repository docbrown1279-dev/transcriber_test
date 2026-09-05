"""Тесты разбиения длинных интервалов и реплик на сегменты (segment splitting)."""

from transcriber.asr.splitter import split_interval, split_turns_into_slices
from transcriber.models.artifacts import TurnItem


def test_d1_spl_01_interval_splits_into_contiguous_slices() -> None:
    """[D1-SPL-01] interval > max_segment_seconds splits on time only into contiguous slices <= max."""
    # Интервал 60 секунд при max_segment_seconds=25.0 должен разбиться на:
    # [0.0, 25.0], [25.0, 50.0], [50.0, 60.0]
    slices = split_interval(start=0.0, end=60.0, max_segment_seconds=25.0)
    assert len(slices) == 3
    assert slices[0] == (0.0, 25.0)
    assert slices[1] == (25.0, 50.0)
    assert slices[2] == (50.0, 60.0)

    # Проверка непрерывности и ограничения длины каждого среза
    for idx in range(len(slices)):
        s, e = slices[idx]
        assert e > s
        assert (e - s) <= 25.0 + 1e-6
        if idx > 0:
            assert s == slices[idx - 1][1]

    # Проверка разбиения через split_turns_into_slices
    turns = [
        TurnItem(id="t0001", start=10.0, end=70.0, speaker="SPEAKER_00"),
        TurnItem(id="t0002", start=70.0, end=80.0, speaker="SPEAKER_01"),
    ]
    turn_slices = split_turns_into_slices(turns, max_segment_seconds=25.0)
    # t0001 (60s) -> 3 среза; t0002 (10s) -> 1 срез; всего 4
    assert len(turn_slices) == 4
    assert [s.turn_id for s in turn_slices] == ["t0001", "t0001", "t0001", "t0002"]
    assert [s.speaker for s in turn_slices] == [
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_00",
        "SPEAKER_01",
    ]
    assert turn_slices[0].start == 10.0
    assert turn_slices[0].end == 35.0
    assert turn_slices[1].start == 35.0
    assert turn_slices[1].end == 60.0
    assert turn_slices[2].start == 60.0
    assert turn_slices[2].end == 70.0
    assert turn_slices[3].start == 70.0
    assert turn_slices[3].end == 80.0

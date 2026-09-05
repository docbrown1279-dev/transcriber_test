"""Тесты слияния реплик дикторов (turn merging & short turn absorption)."""

from transcriber.diarization.merge import merge_turns
from transcriber.models.artifacts import TurnItem


def test_d1_mrg_01_same_speaker_gap_merge() -> None:
    """[D1-MRG-01] same-speaker gap <= config -> merged; larger gap -> kept separate."""
    # Реплики одного диктора с паузой 0.2s (<= 0.3s) должны слиться
    turns_close = [
        TurnItem(id="t0001", start=1.0, end=3.0, speaker="SPEAKER_00"),
        TurnItem(id="t0002", start=3.2, end=5.0, speaker="SPEAKER_00"),
    ]
    merged_close = merge_turns(turns_close, same_speaker_gap_sec=0.3, absorb_shorter_than_sec=0.0)
    assert len(merged_close) == 1
    assert merged_close[0].id == "t0001"
    assert merged_close[0].start == 1.0
    assert merged_close[0].end == 5.0
    assert merged_close[0].speaker == "SPEAKER_00"

    # Реплики одного диктора с паузой 0.5s (> 0.3s) должны остаться раздельными
    turns_far = [
        TurnItem(id="t0001", start=1.0, end=3.0, speaker="SPEAKER_00"),
        TurnItem(id="t0002", start=3.5, end=5.0, speaker="SPEAKER_00"),
    ]
    merged_far = merge_turns(turns_far, same_speaker_gap_sec=0.3, absorb_shorter_than_sec=0.0)
    assert len(merged_far) == 2
    assert merged_far[0].start == 1.0
    assert merged_far[0].end == 3.0
    assert merged_far[1].start == 3.5
    assert merged_far[1].end == 5.0


def test_d1_mrg_02_short_turn_absorbed() -> None:
    """[D1-MRG-02] turn shorter than absorb threshold absorbed into neighbour (prefer same speaker)."""
    # Короткая реплика длительностью 0.5s (< 1.0s) между репликами SPEAKER_00 и SPEAKER_01.
    # Если расстояния равны, предпочтение отдается соседу того же диктора.
    turns = [
        TurnItem(id="t0001", start=0.0, end=4.0, speaker="SPEAKER_00"),
        TurnItem(id="t0002", start=5.0, end=5.5, speaker="SPEAKER_00"),  # Короткая реплика 0.5s
        TurnItem(id="t0003", start=6.5, end=10.0, speaker="SPEAKER_01"),
    ]
    # Пауза слева: 5.0 - 4.0 = 1.0s. Пауза справа: 6.5 - 5.5 = 1.0s.
    # Расстояния равны, но слева SPEAKER_00 == текущий SPEAKER_00.
    merged = merge_turns(turns, same_speaker_gap_sec=0.2, absorb_shorter_than_sec=1.0)
    assert len(merged) == 2
    # Реплика t0002 поглощена в первого диктора (SPEAKER_00)
    assert merged[0].speaker == "SPEAKER_00"
    assert merged[0].start == 0.0
    assert merged[0].end >= 5.5
    assert merged[1].speaker == "SPEAKER_01"

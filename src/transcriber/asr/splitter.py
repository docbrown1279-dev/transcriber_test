"""Разбиение реплик дикторов по времени на сегменты не длиннее max_segment_seconds."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from transcriber.models.artifacts import TurnItem


@dataclass(frozen=True)
class SegmentSlice:
    """Временной срез сегмента реплики."""

    turn_id: str
    speaker: str
    start: float
    end: float


def split_interval(
    start: float,
    end: float,
    max_segment_seconds: float = 25.0,
) -> list[tuple[float, float]]:
    """Разбивает временной интервал на смежные отрезки длиной не более max_segment_seconds."""
    if end <= start:
        return []

    duration = end - start
    if duration <= max_segment_seconds:
        return [(round(start, 3), round(end, 3))]

    slices: list[tuple[float, float]] = []
    curr = start
    while curr < end:
        next_end = min(curr + max_segment_seconds, end)
        s = round(curr, 3)
        e = round(next_end, 3)
        if e > s:
            slices.append((s, e))
        curr = next_end

    return slices


def split_turns_into_slices(
    turns: Sequence[TurnItem | dict[str, Any]],
    max_segment_seconds: float = 25.0,
) -> list[SegmentSlice]:
    """Разбивает список реплик turns на сегменты длиной не более max_segment_seconds."""
    results: list[SegmentSlice] = []
    for turn in turns:
        if isinstance(turn, TurnItem):
            t_id = turn.id
            t_speaker = turn.speaker
            t_start = turn.start
            t_end = turn.end
        elif isinstance(turn, dict):
            t_id = str(turn.get("id", "t0001"))
            t_speaker = str(turn.get("speaker", "SPEAKER_00"))
            t_start = float(turn.get("start", 0.0))
            t_end = float(turn.get("end", 0.0))
        else:
            t_id = str(getattr(turn, "id", "t0001"))
            t_speaker = str(getattr(turn, "speaker", "SPEAKER_00"))
            t_start = float(getattr(turn, "start", 0.0))
            t_end = float(getattr(turn, "end", 0.0))

        intervals = split_interval(t_start, t_end, max_segment_seconds)
        for s, e in intervals:
            results.append(
                SegmentSlice(
                    turn_id=t_id,
                    speaker=t_speaker,
                    start=s,
                    end=e,
                )
            )

    return results

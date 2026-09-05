"""Слияние интервалов речи (VAD) перед эмбеддингом — как в исследовании 1f2."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class Interval:
    """Простой временной интервал [start, end)."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        return self.end - self.start


def merge_speech_regions(
    regions: Sequence[Interval],
    *,
    max_gap_sec: float,
    min_duration_sec: float = 0.0,
) -> list[Interval]:
    """Склеивает соседние речевые регионы с паузой <= max_gap_sec.

    Research 1f2: «VAD-фрагменты склеены gap ≤ 0,3 с до окон». Склейка идёт
    до назначения спикеров — все регионы считаются речью.
    Регионы короче min_duration_sec отбрасываются после склейки.
    """
    if not regions:
        return []

    ordered = sorted(regions, key=lambda r: (r.start, r.end))
    merged: list[Interval] = [Interval(start=ordered[0].start, end=ordered[0].end)]
    for reg in ordered[1:]:
        prev = merged[-1]
        gap = reg.start - prev.end
        if gap <= max_gap_sec:
            merged[-1] = Interval(start=prev.start, end=max(prev.end, reg.end))
        else:
            merged.append(Interval(start=reg.start, end=reg.end))

    if min_duration_sec <= 0:
        return merged
    return [r for r in merged if r.duration >= min_duration_sec]

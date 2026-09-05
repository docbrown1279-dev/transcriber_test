"""Обнаружение и учет пауз (holes) в аудио согласно контракту."""

from collections.abc import Sequence
from typing import Any

from transcriber.models.artifacts import TimeInterval


def find_holes(
    intervals: Sequence[Any],
    total_duration_sec: float | None = None,
    min_hole_sec: float = 0.5,
) -> list[TimeInterval]:
    """Находит паузы между интервалами (и границами аудио), превышающие min_hole_sec.

    Интервалы могут быть объектами с атрибутами start/end или словарями.
    """
    if not intervals:
        if total_duration_sec is not None and total_duration_sec >= min_hole_sec:
            return [TimeInterval(start=0.0, end=round(total_duration_sec, 3))]
        return []

    # Приводим к кортежам (start, end), отсортированным по start
    raw_intervals: list[tuple[float, float]] = []
    for item in intervals:
        if hasattr(item, "start") and hasattr(item, "end"):
            s, e = float(item.start), float(item.end)
        elif isinstance(item, dict) and "start" in item and "end" in item:
            s, e = float(item["start"]), float(item["end"])
        else:
            continue
        if e > s:
            raw_intervals.append((s, e))

    raw_intervals.sort(key=lambda x: x[0])
    if not raw_intervals:
        if total_duration_sec is not None and total_duration_sec >= min_hole_sec:
            return [TimeInterval(start=0.0, end=round(total_duration_sec, 3))]
        return []

    holes: list[TimeInterval] = []

    # 1. Проверяем паузу до первого интервала
    first_start = raw_intervals[0][0]
    if first_start >= min_hole_sec:
        holes.append(TimeInterval(start=0.0, end=round(first_start, 3)))

    # 2. Проверяем паузы между соседними интервалами
    current_end = raw_intervals[0][1]
    for start, end in raw_intervals[1:]:
        gap = start - current_end
        if gap >= min_hole_sec:
            holes.append(TimeInterval(start=round(current_end, 3), end=round(start, 3)))
        if end > current_end:
            current_end = end

    # 3. Проверяем паузу после последнего интервала
    if total_duration_sec is not None:
        trailing_gap = total_duration_sec - current_end
        if trailing_gap >= min_hole_sec:
            holes.append(
                TimeInterval(start=round(current_end, 3), end=round(total_duration_sec, 3))
            )

    return holes

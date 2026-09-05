"""Слияние реплик дикторов: склейка пауз одного диктора и поглощение коротких реплик."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from transcriber.models.artifacts import TurnItem


@dataclass
class _MutableTurn:
    start: float
    end: float
    speaker: str


def _merge_same_speaker_gaps(
    turns: list[_MutableTurn],
    max_gap: float,
) -> list[_MutableTurn]:
    """Объединяет соседние реплики одного диктора с паузой <= max_gap."""
    if not turns:
        return []

    merged: list[_MutableTurn] = [turns[0]]
    for t in turns[1:]:
        prev = merged[-1]
        gap = t.start - prev.end
        if t.speaker == prev.speaker and gap <= max_gap:
            prev.start = min(prev.start, t.start)
            prev.end = max(prev.end, t.end)
        else:
            merged.append(t)
    return merged


def _absorb_short_turns(
    turns: list[_MutableTurn],
    min_duration: float,
) -> list[_MutableTurn]:
    """Поглощает реплики короче min_duration в ближайшего соседа.

    При равном расстоянии отдается предпочтение соседу с тем же диктором.
    """
    if len(turns) <= 1:
        return turns

    i = 0
    while i < len(turns):
        curr = turns[i]
        dur = curr.end - curr.start
        if dur < min_duration and len(turns) > 1:
            # Есть ли левый и правый соседи
            has_left = i > 0
            has_right = i < len(turns) - 1

            target_idx: int
            if has_left and has_right:
                dist_left = curr.start - turns[i - 1].end
                dist_right = turns[i + 1].start - curr.end

                if dist_left < dist_right:
                    target_idx = i - 1
                elif dist_right < dist_left:
                    target_idx = i + 1
                else:
                    # При равенстве предпочитаем того же диктора
                    if turns[i - 1].speaker == curr.speaker:
                        target_idx = i - 1
                    elif turns[i + 1].speaker == curr.speaker:
                        target_idx = i + 1
                    else:
                        target_idx = i - 1
            elif has_left:
                target_idx = i - 1
            else:
                target_idx = i + 1

            target = turns[target_idx]
            target.start = min(target.start, curr.start)
            target.end = max(target.end, curr.end)

            turns.pop(i)
            # Если поглотили в соседа слева, следующий шаг останется на индексе i (бывшем i+1)
            # Если поглотили в соседа справа, остаемся на индексе i
            if target_idx < i:
                i = max(0, i - 1)
        else:
            i += 1

    return turns


def merge_turns(
    turns: Sequence[Any],
    same_speaker_gap_sec: float = 0.3,
    absorb_shorter_than_sec: float = 1.0,
) -> list[TurnItem]:
    """Выполняет строго последовательное слияние реплик согласно контракту.

    1. Склейка соседних реплик одного диктора с паузой <= same_speaker_gap_sec.
    2. Поглощение реплик короче absorb_shorter_than_sec в ближайшего соседа.
    3. Повторная склейка одного диктора при необходимости.
    4. Присвоение стабильных идентификаторов t0001, t0002, ...
    """
    if not turns:
        return []

    # Конвертируем входные данные
    raw_list: list[_MutableTurn] = []
    for item in turns:
        if isinstance(item, TurnItem):
            raw_list.append(_MutableTurn(start=item.start, end=item.end, speaker=item.speaker))
        elif hasattr(item, "start") and hasattr(item, "end") and hasattr(item, "speaker"):
            raw_list.append(
                _MutableTurn(
                    start=float(item.start),
                    end=float(item.end),
                    speaker=str(item.speaker),
                )
            )
        elif isinstance(item, dict):
            raw_list.append(
                _MutableTurn(
                    start=float(item["start"]),
                    end=float(item["end"]),
                    speaker=str(item["speaker"]),
                )
            )

    raw_list.sort(key=lambda t: t.start)

    # Шаг 1: Склейка того же диктора
    step1 = _merge_same_speaker_gaps(raw_list, same_speaker_gap_sec)

    # Шаг 2: Поглощение коротких реплик
    step2 = _absorb_short_turns(step1, absorb_shorter_than_sec)

    # Шаг 3: Повторная склейка того же диктора
    step3 = _merge_same_speaker_gaps(step2, same_speaker_gap_sec)

    # Формируем результат с монотонными таймкодами и идентификаторами
    result: list[TurnItem] = []
    prev_start = 0.0
    for idx, item in enumerate(step3, start=1):
        s = round(max(prev_start, item.start), 3)
        e = round(max(s + 0.001, item.end), 3)
        result.append(
            TurnItem(
                id=f"t{idx:04d}",
                start=s,
                end=e,
                speaker=item.speaker,
            )
        )
        prev_start = s

    return result

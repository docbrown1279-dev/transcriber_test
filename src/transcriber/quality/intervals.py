"""Interval IoU helpers for speech-region regression checks."""

from __future__ import annotations

from collections.abc import Sequence


def _merge(intervals: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    ordered = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not ordered:
        return []
    merged: list[list[float]] = [[ordered[0][0], ordered[0][1]]]
    for start, end in ordered[1:]:
        if start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(a, b) for a, b in merged]


def _covered(intervals: Sequence[tuple[float, float]]) -> float:
    return sum(b - a for a, b in intervals)


def _intersection(
    a: Sequence[tuple[float, float]],
    b: Sequence[tuple[float, float]],
) -> float:
    i = j = 0
    total = 0.0
    aa = list(a)
    bb = list(b)
    while i < len(aa) and j < len(bb):
        start = max(aa[i][0], bb[j][0])
        end = min(aa[i][1], bb[j][1])
        if end > start:
            total += end - start
        if aa[i][1] < bb[j][1]:
            i += 1
        else:
            j += 1
    return total


def speech_regions_iou(
    reference: Sequence[tuple[float, float]],
    hypothesis: Sequence[tuple[float, float]],
) -> float:
    """Return intersection-over-union of two speech region sets (merged)."""
    ref = _merge(reference)
    hyp = _merge(hypothesis)
    inter = _intersection(ref, hyp)
    union = _covered(ref) + _covered(hyp) - inter
    if union <= 0:
        return 1.0 if not ref and not hyp else 0.0
    return inter / union

"""Pause-based cut planner for TTFT file-split (ported from scripts/plan_pause_cuts.py)."""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class Pause:
    start: float
    end: float
    duration: float
    mid: float


@dataclass(frozen=True)
class Cut:
    t: float
    pause_start: float
    pause_end: float
    pause_duration: float
    ideal_t: float
    offset_from_ideal: float


def pauses_from_regions(
    regions: list[tuple[float, float]],
    *,
    duration_sec: float,
    min_pause_sec: float,
) -> list[Pause]:
    """Gaps between speech regions (and file edges) longer than min_pause_sec."""
    out: list[Pause] = []
    cursor = 0.0
    for start, end in regions:
        if start > cursor + 1e-6:
            gap = start - cursor
            if gap >= min_pause_sec:
                out.append(
                    Pause(
                        start=round(cursor, 3),
                        end=round(start, 3),
                        duration=round(gap, 3),
                        mid=round((cursor + start) / 2.0, 3),
                    )
                )
        cursor = max(cursor, end)
    if duration_sec > cursor + 1e-6:
        gap = duration_sec - cursor
        if gap >= min_pause_sec:
            out.append(
                Pause(
                    start=round(cursor, 3),
                    end=round(duration_sec, 3),
                    duration=round(gap, 3),
                    mid=round((cursor + duration_sec) / 2.0, 3),
                )
            )
    return out


def _score_pause(pause: Pause, ideal_t: float, *, search_half_width: float) -> float:
    """Higher is better: long pause, close to ideal, inside search window."""
    dist = abs(pause.mid - ideal_t)
    if dist > search_half_width:
        return float("-inf")
    return pause.duration - 0.15 * dist


def choose_cuts(
    pauses: list[Pause],
    *,
    duration_sec: float,
    n_parts: int,
    min_part_sec: float,
    max_part_sec: float,
    search_half_width: float,
) -> list[Cut]:
    if n_parts < 2:
        raise ValueError("n_parts must be >= 2")
    ideal_len = duration_sec / n_parts
    cuts: list[Cut] = []
    used_mids: set[float] = set()

    for i in range(1, n_parts):
        ideal_t = ideal_len * i
        earliest = cuts[-1].t + min_part_sec if cuts else min_part_sec
        latest = duration_sec - min_part_sec * (n_parts - i)
        soft_latest = (cuts[-1].t + max_part_sec) if cuts else max_part_sec
        latest = min(latest, max(soft_latest, earliest))

        candidates = [
            p for p in pauses if earliest <= p.mid <= latest and p.mid not in used_mids
        ]
        best: Pause | None = None
        best_score = float("-inf")
        for p in candidates:
            score = _score_pause(p, ideal_t, search_half_width=search_half_width)
            if score > best_score:
                best_score = score
                best = p

        if best is None:
            window = [p for p in pauses if earliest <= p.mid <= latest]
            if window:
                best = max(window, key=lambda p: (p.duration, -abs(p.mid - ideal_t)))
            else:
                # Impossible / empty window (over-constrained n_parts) → clamp to band.
                if earliest > latest + 1e-6:
                    t = min(max(ideal_t, min_part_sec), duration_sec - min_part_sec)
                    t = max(earliest if cuts else min_part_sec, min(t, duration_sec - 1e-3))
                else:
                    t = min(max(ideal_t, earliest), latest)
                cuts.append(
                    Cut(
                        t=round(t, 3),
                        pause_start=round(t, 3),
                        pause_end=round(t, 3),
                        pause_duration=0.0,
                        ideal_t=round(ideal_t, 3),
                        offset_from_ideal=round(t - ideal_t, 3),
                    )
                )
                continue

        used_mids.add(best.mid)
        cuts.append(
            Cut(
                t=best.mid,
                pause_start=best.start,
                pause_end=best.end,
                pause_duration=best.duration,
                ideal_t=round(ideal_t, 3),
                offset_from_ideal=round(best.mid - ideal_t, 3),
            )
        )
    return cuts


def parts_from_cuts(cuts: list[Cut], duration_sec: float) -> list[dict[str, Any]]:
    bounds = [0.0, *[c.t for c in cuts], duration_sec]
    parts: list[dict[str, Any]] = []
    for i in range(len(bounds) - 1):
        start, end = bounds[i], bounds[i + 1]
        parts.append(
            {
                "id": f"part{i + 1:02d}",
                "index": i,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration_sec": round(end - start, 3),
            }
        )
    return parts


def coalesce_short_parts(
    parts: list[dict[str, Any]],
    *,
    min_part_sec: float,
) -> list[dict[str, Any]]:
    """Merge parts shorter than ``min_part_sec`` into a neighbour (prefer next, else prev)."""
    if len(parts) <= 1:
        return list(parts)
    work = [
        {
            "start": float(p["start"]),
            "end": float(p["end"]),
            "duration_sec": float(p["duration_sec"]),
        }
        for p in parts
    ]
    changed = True
    while changed and len(work) > 1:
        changed = False
        for i, part in enumerate(work):
            if part["duration_sec"] + 1e-9 >= min_part_sec:
                continue
            # Prefer merging into the next part; last crumb → previous.
            if i < len(work) - 1:
                nxt = work[i + 1]
                merged = {
                    "start": part["start"],
                    "end": nxt["end"],
                    "duration_sec": round(nxt["end"] - part["start"], 3),
                }
                work = [*work[:i], merged, *work[i + 2 :]]
            else:
                prev = work[i - 1]
                merged = {
                    "start": prev["start"],
                    "end": part["end"],
                    "duration_sec": round(part["end"] - prev["start"], 3),
                }
                work = [*work[: i - 1], merged]
            changed = True
            break
    return [
        {
            "id": f"part{i + 1:02d}",
            "index": i,
            "start": round(p["start"], 3),
            "end": round(p["end"], 3),
            "duration_sec": round(p["duration_sec"], 3),
        }
        for i, p in enumerate(work)
    ]


def propose_n_parts(
    duration_sec: float,
    *,
    min_part_sec: float,
    max_part_sec: float,
    target_part_sec: float,
) -> int:
    """Choose part count from duration and [min,max,target] constraints.

    Uses a small epsilon so float wav durations barely above N*max_part_sec
    do not spuriously force an extra part (which then collapses into a crumb).
    """
    if duration_sec < 2 * min_part_sec:
        return 1
    eps = 1e-3
    lo = max(2, math.ceil(duration_sec / max_part_sec - eps))
    hi = max(lo, math.floor(duration_sec / min_part_sec + eps))
    ideal = int(round(duration_sec / target_part_sec))
    return max(lo, min(hi, ideal))


def plan(
    regions: list[tuple[float, float]],
    *,
    duration_sec: float,
    n_parts: int,
    min_part_sec: float,
    max_part_sec: float,
    min_pause_sec: float,
    search_half_width: float,
) -> dict[str, Any]:
    pauses = pauses_from_regions(
        regions, duration_sec=duration_sec, min_pause_sec=min_pause_sec
    )
    cuts = choose_cuts(
        pauses,
        duration_sec=duration_sec,
        n_parts=n_parts,
        min_part_sec=min_part_sec,
        max_part_sec=max_part_sec,
        search_half_width=search_half_width,
    )
    parts = coalesce_short_parts(
        parts_from_cuts(cuts, duration_sec),
        min_part_sec=min_part_sec,
    )
    # Prefer original pause metadata when a coalesced boundary still matches a cut.
    by_t = {round(c.t, 3): asdict(c) for c in cuts}
    cuts_out: list[dict[str, Any]] = []
    for i in range(len(parts) - 1):
        t = round(float(parts[i]["end"]), 3)
        if t in by_t:
            cuts_out.append(by_t[t])
        else:
            cuts_out.append(
                {
                    "t": t,
                    "pause_start": t,
                    "pause_end": t,
                    "pause_duration": 0.0,
                    "ideal_t": t,
                    "offset_from_ideal": 0.0,
                }
            )
    durations = [p["duration_sec"] for p in parts]
    return {
        "schema_version": "1",
        "algorithm": "silero_pause_balanced",
        "duration_sec": round(duration_sec, 3),
        "n_parts": len(parts),
        "constraints": {
            "min_part_sec": min_part_sec,
            "max_part_sec": max_part_sec,
            "min_pause_sec": min_pause_sec,
            "search_half_width_sec": search_half_width,
        },
        "pause_count_ge_min": len(pauses),
        "top_pauses": [
            asdict(p) for p in sorted(pauses, key=lambda x: x.duration, reverse=True)[:15]
        ],
        "cuts": cuts_out,
        "parts": parts,
        "metrics": {
            "part_durations_sec": durations,
            "min_part_sec": min(durations) if durations else 0.0,
            "max_part_sec": max(durations) if durations else 0.0,
            "spread_sec": round(max(durations) - min(durations), 3) if durations else 0.0,
            "all_in_range": all(min_part_sec <= d <= max_part_sec for d in durations),
            "requested_n_parts": n_parts,
        },
    }

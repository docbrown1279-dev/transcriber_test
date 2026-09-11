#!/usr/bin/env python3
"""Plan roughly equal audio parts cut at long Silero pauses (TTFT S2).

Reads speech regions (speech.json from a prior job, or inline JSON) and picks
N-1 cut points so each part lands in [min_part, max_part] seconds when possible,
preferring the longest pause near each ideal boundary.

Does not mutate audio; writes a cut plan JSON (+ optional markdown summary).
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
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


def _load_regions(path: Path) -> list[tuple[float, float]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "regions" in data:
        raw = data["regions"]
    elif isinstance(data, list):
        raw = data
    else:
        raise ValueError(f"unsupported speech JSON shape in {path}")
    regions: list[tuple[float, float]] = []
    for item in raw:
        regions.append((float(item["start"]), float(item["end"])))
    regions.sort(key=lambda x: x[0])
    return regions


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
    # Prefer duration, lightly penalize distance (seconds).
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
        # Keep remaining parts feasible: leave room for later min_part slices.
        earliest = cuts[-1].t + min_part_sec if cuts else min_part_sec
        latest = duration_sec - min_part_sec * (n_parts - i)
        # Soft max: prefer not exceeding max_part from previous cut.
        soft_latest = (cuts[-1].t + max_part_sec) if cuts else max_part_sec
        latest = min(latest, max(soft_latest, earliest))

        candidates = [
            p
            for p in pauses
            if earliest <= p.mid <= latest and p.mid not in used_mids
        ]
        best: Pause | None = None
        best_score = float("-inf")
        for p in candidates:
            score = _score_pause(p, ideal_t, search_half_width=search_half_width)
            if score > best_score:
                best_score = score
                best = p

        if best is None:
            # Fallback: longest pause in the feasible window, else hard midpoint.
            window = [p for p in pauses if earliest <= p.mid <= latest]
            if window:
                best = max(window, key=lambda p: (p.duration, -abs(p.mid - ideal_t)))
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


def propose_n_parts(
    duration_sec: float,
    *,
    min_part_sec: float,
    max_part_sec: float,
    prefer_n: int | None,
) -> int:
    if prefer_n is not None:
        return prefer_n
    lo = max(2, math.ceil(duration_sec / max_part_sec))
    hi = max(lo, math.floor(duration_sec / min_part_sec))
    # Prefer mid of feasible band, clipped to 3..5 when possible.
    preferred = sorted(range(lo, hi + 1), key=lambda n: (abs(n - 4), n))
    for n in preferred:
        if 3 <= n <= 5:
            return n
    return preferred[0] if preferred else 3


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
    parts = parts_from_cuts(cuts, duration_sec)
    durations = [p["duration_sec"] for p in parts]
    return {
        "schema_version": "1",
        "algorithm": "silero_pause_balanced",
        "duration_sec": round(duration_sec, 3),
        "n_parts": n_parts,
        "constraints": {
            "min_part_sec": min_part_sec,
            "max_part_sec": max_part_sec,
            "min_pause_sec": min_pause_sec,
            "search_half_width_sec": search_half_width,
        },
        "pause_count_ge_min": len(pauses),
        "top_pauses": [
            asdict(p)
            for p in sorted(pauses, key=lambda x: x.duration, reverse=True)[:15]
        ],
        "cuts": [asdict(c) for c in cuts],
        "parts": parts,
        "metrics": {
            "part_durations_sec": durations,
            "min_part_sec": min(durations) if durations else 0.0,
            "max_part_sec": max(durations) if durations else 0.0,
            "spread_sec": round(max(durations) - min(durations), 3) if durations else 0.0,
            "all_in_range": all(min_part_sec <= d <= max_part_sec for d in durations),
        },
    }


def _md_summary(plan_obj: dict[str, Any]) -> str:
    lines = [
        f"# Pause cut plan ({plan_obj['n_parts']} parts)",
        "",
        f"- duration: {plan_obj['duration_sec']:.1f}s",
        f"- parts in [{plan_obj['constraints']['min_part_sec']},"
        f" {plan_obj['constraints']['max_part_sec']}]s:"
        f" {'YES' if plan_obj['metrics']['all_in_range'] else 'NO'}",
        f"- spread: {plan_obj['metrics']['spread_sec']}s",
        "",
        "| part | start | end | dur_s |",
        "|---|---:|---:|---:|",
    ]
    for p in plan_obj["parts"]:
        lines.append(
            f"| {p['id']} | {p['start']:.1f} | {p['end']:.1f} | {p['duration_sec']:.1f} |"
        )
    lines.extend(["", "## Cuts", ""])
    for i, c in enumerate(plan_obj["cuts"], start=1):
        lines.append(
            f"- cut{i}: t={c['t']:.1f}s (ideal {c['ideal_t']:.1f},"
            f" Δ={c['offset_from_ideal']:+.1f}),"
            f" pause={c['pause_duration']:.2f}s"
            f" [{c['pause_start']:.1f}–{c['pause_end']:.1f}]"
        )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--speech-json", type=Path, required=True)
    ap.add_argument("--duration-sec", type=float, required=True)
    ap.add_argument("--n-parts", type=int, default=None)
    ap.add_argument("--min-part-sec", type=float, default=180.0)
    ap.add_argument("--max-part-sec", type=float, default=360.0)
    ap.add_argument("--min-pause-sec", type=float, default=0.8)
    ap.add_argument("--search-half-width-sec", type=float, default=90.0)
    ap.add_argument("--out-json", type=Path, required=True)
    ap.add_argument("--out-md", type=Path, default=None)
    args = ap.parse_args()

    regions = _load_regions(args.speech_json)
    # Clip regions to requested duration (e.g. 15 min slice of full-meeting speech).
    clipped: list[tuple[float, float]] = []
    for start, end in regions:
        if start >= args.duration_sec:
            continue
        clipped.append((start, min(end, args.duration_sec)))

    n_parts = propose_n_parts(
        args.duration_sec,
        min_part_sec=args.min_part_sec,
        max_part_sec=args.max_part_sec,
        prefer_n=args.n_parts,
    )
    plan_obj = plan(
        clipped,
        duration_sec=args.duration_sec,
        n_parts=n_parts,
        min_part_sec=args.min_part_sec,
        max_part_sec=args.max_part_sec,
        min_pause_sec=args.min_pause_sec,
        search_half_width=args.search_half_width_sec,
    )

    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(plan_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    md = _md_summary(plan_obj)
    if args.out_md is not None:
        args.out_md.parent.mkdir(parents=True, exist_ok=True)
        args.out_md.write_text(md, encoding="utf-8")
    print(md)
    print(f"wrote {args.out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

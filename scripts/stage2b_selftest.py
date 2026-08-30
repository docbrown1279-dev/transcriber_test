#!/usr/bin/env python3
"""Validator self-check on synthetic chapters. No models, no audio."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import json

from stage2b_common import TIMING_METHOD, validate_chapters


def leaves() -> list[dict]:
    return [
        {"id": 0, "start": 1.5, "end": 3.0, "text": "a", "speakers": ["S"]},
        {"id": 1, "start": 3.2, "end": 5.0, "text": "b", "speakers": ["S"]},
        {"id": 2, "start": 5.1, "end": 8.0, "text": "c", "speakers": ["S"]},
    ]


def chapter(ids: list[int], start: float, end: float, source: str) -> dict:
    return {
        "id": ids[0],
        "start": start,
        "end": end,
        "source_ids": ids,
        "leaf_ids": ids,
        "start_source_id": ids[0],
        "end_source_id": ids[-1],
        "timing_source": source,
        "timing_method": TIMING_METHOD,
    }


def main() -> None:
    source = "synthetic.json"
    good = [
        chapter([0], 1.5, 3.0, source),
        chapter([1, 2], 3.2, 8.0, source),
    ]
    ok = validate_chapters(good, leaves(), timing_source=source)
    bad_time = [
        chapter([0], 1.4, 3.0, source),
        chapter([1, 2], 3.2, 8.0, source),
    ]
    bad_gap = [
        chapter([0], 1.5, 3.0, source),
        chapter([2], 5.1, 8.0, source),
    ]
    bad_order = [
        chapter([1, 2], 3.2, 8.0, source),
        chapter([0], 1.5, 3.0, source),
    ]
    report = {
        "good_ok": ok["ok"],
        "bad_time_rejected": not validate_chapters(bad_time, leaves(), timing_source=source)["ok"],
        "bad_gap_rejected": not validate_chapters(bad_gap, leaves(), timing_source=source)["ok"],
        "bad_order_rejected": not validate_chapters(bad_order, leaves(), timing_source=source)["ok"],
    }
    report["ok"] = all(report.values())
    print(json.dumps(report, ensure_ascii=False))
    if not report["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

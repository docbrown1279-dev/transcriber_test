#!/usr/bin/env python3
"""Write a combined source-boundary validation report for A–D."""

from __future__ import annotations

import json
from pathlib import Path

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

from stage2b_common import (
    OUT_DIR,
    TIMING_SOURCE_AB,
    TIMING_SOURCE_CD,
    load_asr_leaves,
    load_titled_leaves,
    validate_chapters,
    write_json,
)


def load_chapters(path: Path) -> list[dict] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") == "skipped":
        return []
    return payload.get("chapters")


def main() -> None:
    titled = load_titled_leaves()
    asr = load_asr_leaves()
    jobs = {
        "A": (OUT_DIR / "exp_a_chapters.json", titled, TIMING_SOURCE_AB),
        "B": (OUT_DIR / "exp_b_chapters.json", titled, TIMING_SOURCE_AB),
        "C": (OUT_DIR / "exp_c_chapters.json", asr, TIMING_SOURCE_CD),
        "D": (OUT_DIR / "exp_d_chapters.json", asr, TIMING_SOURCE_CD),
    }
    report = {}
    for name, (path, leaves, source) in jobs.items():
        chapters = load_chapters(path)
        if chapters is None:
            skipped = OUT_DIR / "exp_d_skipped.json"
            if name == "D" and skipped.exists():
                report[name] = {
                    "ok": False,
                    "skipped": True,
                    "reason": json.loads(skipped.read_text(encoding="utf-8")).get("error"),
                }
            else:
                report[name] = {"ok": False, "pending": True}
            continue
        report[name] = validate_chapters(chapters, leaves, timing_source=source)
    write_json(OUT_DIR / "timestamp_validation.json", report)
    print(json.dumps({k: {"ok": v.get("ok"), "n": v.get("n_chapters"), "skipped": v.get("skipped")} for k, v in report.items()}))


if __name__ == "__main__":
    main()

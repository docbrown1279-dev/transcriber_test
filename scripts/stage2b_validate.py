#!/usr/bin/env python3
"""Deterministic Stage 2b source-id and timestamp validator."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import argparse
import json
from pathlib import Path

from stage2b_common import (
    OUT_DIR,
    TIMING_SOURCE_AB,
    TIMING_SOURCE_CD,
    load_asr_leaves,
    load_titled_leaves,
    validate_chapters,
    write_json,
)


def load_chapters(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and "chapters" in payload:
        return payload["chapters"]
    if isinstance(payload, dict) and "candidates" in payload:
        raise SystemExit("pass a per-experiment chapters file, not the bundle")
    raise SystemExit(f"no chapters in {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chapters", type=Path, required=True)
    parser.add_argument("--source", required=True, choices=["ab", "cd"])
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    chapters = load_chapters(args.chapters)
    if args.source == "ab":
        leaves = load_titled_leaves()
        timing_source = TIMING_SOURCE_AB
    else:
        leaves = load_asr_leaves()
        timing_source = TIMING_SOURCE_CD
    result = validate_chapters(chapters, leaves, timing_source=timing_source)
    out = args.out or OUT_DIR / "validation_manual.json"
    write_json(out, result)
    print(json.dumps({"ok": result["ok"], "errors": result["errors"], "n": result["n_chapters"]}))
    if not result["ok"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

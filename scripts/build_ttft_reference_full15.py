#!/usr/bin/env python3
"""Build gitignored eval/d5_ttft_split/reference_full15 from full15 artifacts.

Not manual gold — slices cloud_out/artifacts/full15 by cut_plan_15min_3.
Absolute timestamps are preserved. Overlap rule: start < part_end AND end > part_start.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dump(path: Path, doc: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _overlaps(start: float, end: float, win_start: float, win_end: float) -> bool:
    return start < win_end and end > win_start


def _filter_timed(
    items: list[dict[str, Any]], win_start: float, win_end: float
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in items:
        if _overlaps(float(item["start"]), float(item["end"]), win_start, win_end):
            out.append(item)
    return out


def _part_meta(part: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": part["id"],
        "index": part["index"],
        "start": float(part["start"]),
        "end": float(part["end"]),
        "duration_sec": float(part["duration_sec"]),
    }


def slice_transcript(
    full: dict[str, Any], part: dict[str, Any]
) -> dict[str, Any]:
    win_s, win_e = float(part["start"]), float(part["end"])
    segs = _filter_timed(list(full.get("segments") or []), win_s, win_e)
    holes = _filter_timed(list(full.get("holes") or []), win_s, win_e)
    text_concat = " ".join((s.get("text") or "").strip() for s in segs if not s.get("empty"))
    out = {
        "schema_version": full.get("schema_version", "1"),
        "reference": "full15_window",
        "not_manual_gold": True,
        "source_job_id": full.get("job_id"),
        "part": _part_meta(part),
        "engine": full.get("engine"),
        "language": full.get("language"),
        "text_concat": text_concat,
        "holes": holes,
        "segments": segs,
        "n_segments": len(segs),
    }
    return out


def slice_chapters(full: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    win_s, win_e = float(part["start"]), float(part["end"])
    chapters = _filter_timed(list(full.get("chapters") or []), win_s, win_e)
    return {
        "schema_version": full.get("schema_version", "1"),
        "reference": "full15_window",
        "not_manual_gold": True,
        "source_job_id": full.get("job_id"),
        "part": _part_meta(part),
        "chunker": full.get("chunker"),
        "embedding_model": full.get("embedding_model"),
        "similarity_threshold": full.get("similarity_threshold"),
        "chapters": chapters,
        "n_chapters": len(chapters),
    }


def slice_turns(full: dict[str, Any], part: dict[str, Any]) -> dict[str, Any]:
    win_s, win_e = float(part["start"]), float(part["end"])
    turns = _filter_timed(list(full.get("turns") or []), win_s, win_e)
    holes = _filter_timed(list(full.get("holes") or []), win_s, win_e)
    speakers = sorted({t.get("speaker") for t in turns if t.get("speaker")})
    return {
        "schema_version": full.get("schema_version", "1"),
        "reference": "full15_window",
        "not_manual_gold": True,
        "source_job_id": full.get("job_id"),
        "part": _part_meta(part),
        "diarizer": full.get("diarizer"),
        "merge": full.get("merge"),
        "holes": holes,
        "turns": turns,
        "n_turns": len(turns),
        "speaker_ids": speakers,
        "speaker_count": len(speakers),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--full15-dir",
        type=Path,
        default=Path("cloud_out/artifacts/full15"),
    )
    ap.add_argument(
        "--cut-plan",
        type=Path,
        default=Path("cloud_in/inputs/artifacts/cut_plan_15min_3.json"),
    )
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path("eval/d5_ttft_split/reference_full15"),
    )
    ap.add_argument("--git-rev", type=str, default="")
    args = ap.parse_args()

    cut = _load(args.cut_plan)
    parts = list(cut["parts"])
    transcript = _load(args.full15_dir / "transcript.json")
    chapters = _load(args.full15_dir / "chapters.json")
    turns = _load(args.full15_dir / "turns.json")

    out = args.out_dir
    out.mkdir(parents=True, exist_ok=True)

    for name, src in (
        ("full_transcript.json", args.full15_dir / "transcript.json"),
        ("full_chapters.json", args.full15_dir / "chapters.json"),
        ("full_turns.json", args.full15_dir / "turns.json"),
    ):
        shutil.copy2(src, out / name)

    # thin provenance sidecar next to copies (does not alter schema of full_*)
    provenance = {
        "schema_version": "1",
        "not_manual_gold": True,
        "kind": "full15_pipeline_artifacts",
        "source_dir": str(args.full15_dir),
        "source_job_id": transcript.get("job_id") or "full15_job",
        "job_dir": "cloud_out/artifacts/full15_job",
        "audio": "cloud_in/inputs/audio/voice_002_15min.m4a",
        "cut_plan": str(args.cut_plan),
        "cut_parts": [_part_meta(p) for p in parts],
        "git_rev": args.git_rev or None,
        "notes": [
            "Copied from full15 ASR/diar/packing artifacts; not eval/d5_diar/gold.",
            "Part windows keep absolute timestamps; overlap = start < end AND end > start.",
        ],
    }
    _dump(out / "provenance.json", provenance)

    for part in parts:
        pid = part["id"]
        _dump(out / f"{pid}_transcript.json", slice_transcript(transcript, part))
        _dump(out / f"{pid}_chapters.json", slice_chapters(chapters, part))
        _dump(out / f"{pid}_turns.json", slice_turns(turns, part))

    print(f"wrote {out} parts={[p['id'] for p in parts]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Compare 1f diarizer turns to Stage 1e pyannote 3.1 (not human gold)."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CLIPS = [
    ("test_voice", 83.0),
    ("test_apartments", 85.0),
    ("test_transformers", 85.0),
    ("test_ninth", 85.0),
]
FRAME = 0.01
COLLAR = 0.25


def load_turns(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "merged_turns" in data:
        rows = data["merged_turns"]
    elif "raw_turns" in data:
        rows = data["raw_turns"]
    else:
        rows = [
            {"start": s["start"], "end": s["end"], "speaker": s.get("speaker", "UNK")}
            for s in data.get("segments", [])
        ]
    return [
        {"start": float(r["start"]), "end": float(r["end"]), "speaker": str(r["speaker"])}
        for r in rows
        if float(r["end"]) > float(r["start"])
    ]


def frames(turns: list[dict[str, Any]], duration: float) -> list[str | None]:
    n = int(round(duration / FRAME))
    out: list[str | None] = [None] * n
    for turn in turns:
        a = max(0, int(turn["start"] / FRAME))
        b = min(n, int(turn["end"] / FRAME))
        for i in range(a, b):
            out[i] = turn["speaker"]
    return out


def collar_mask(ref_turns: list[dict[str, Any]], duration: float) -> list[bool]:
    n = int(round(duration / FRAME))
    ignore = [False] * n
    for turn in ref_turns:
        for edge in (turn["start"], turn["end"]):
            a = max(0, int((edge - COLLAR) / FRAME))
            b = min(n, int((edge + COLLAR) / FRAME))
            for i in range(a, b):
                ignore[i] = True
    return ignore


def map_speakers(ref: list[str | None], hyp: list[str | None]) -> dict[str, str]:
    ref_ids = sorted({x for x in ref if x})
    hyp_ids = sorted({x for x in hyp if x})
    overlap: dict[tuple[str, str], int] = {}
    for r, h in zip(ref, hyp):
        if r and h:
            overlap[(r, h)] = overlap.get((r, h), 0) + 1
    mapping: dict[str, str] = {}
    used_ref: set[str] = set()
    used_hyp: set[str] = set()
    pairs = sorted(overlap.items(), key=lambda item: -item[1])
    for (r, h), _ in pairs:
        if r in used_ref or h in used_hyp:
            continue
        mapping[h] = r
        used_ref.add(r)
        used_hyp.add(h)
    leftover = 0
    for h in hyp_ids:
        if h not in mapping:
            mapping[h] = f"UNMAPPED_{leftover}"
            leftover += 1
    return mapping


def score(ref_turns: list[dict[str, Any]], hyp_turns: list[dict[str, Any]], duration: float) -> dict[str, Any]:
    ref_f = frames(ref_turns, duration)
    hyp_f = frames(hyp_turns, duration)
    mapping = map_speakers(ref_f, hyp_f)
    mapped = [mapping[s] if s else None for s in hyp_f]
    ignore = collar_mask(ref_turns, duration)

    def accumulate(use_collar: bool) -> dict[str, float]:
        miss = fa = conf = ref_speech = 0
        for i, (r, h) in enumerate(zip(ref_f, mapped)):
            if use_collar and ignore[i]:
                continue
            if r:
                ref_speech += 1
            if r and not h:
                miss += 1
            elif h and not r:
                fa += 1
            elif r and h and r != h:
                conf += 1
        speech_and = sum(1 for r, h in zip(ref_f, hyp_f) if r and h)
        speech_or = sum(1 for r, h in zip(ref_f, hyp_f) if r or h)
        return {
            "miss_sec": round(miss * FRAME, 3),
            "false_alarm_sec": round(fa * FRAME, 3),
            "confusion_sec": round(conf * FRAME, 3),
            "ref_speech_sec": round(ref_speech * FRAME, 3),
            "der": round((miss + fa + conf) / ref_speech, 4) if ref_speech else None,
            "speech_iou": round(speech_and / speech_or, 4) if speech_or else None,
        }

    ref_speakers = sorted({t["speaker"] for t in ref_turns})
    hyp_speakers = sorted({t["speaker"] for t in hyp_turns})
    return {
        "n_ref_turns": len(ref_turns),
        "n_hyp_turns": len(hyp_turns),
        "n_ref_speakers": len(ref_speakers),
        "n_hyp_speakers": len(hyp_speakers),
        "speaker_map_hyp_to_ref": mapping,
        "raw": accumulate(False),
        "collar_0_25": accumulate(True),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hyp-dir",
        action="append",
        required=True,
        help="results/asr/1f/<diarizer_id> (repeat)",
    )
    parser.add_argument(
        "--ref-dir",
        default=str(ROOT / "results/reports/1f/baseline/pyannote31"),
    )
    parser.add_argument(
        "--out",
        default=str(ROOT / "results/reports/1f/turn_compare.json"),
    )
    args = parser.parse_args()
    ref_dir = Path(args.ref_dir)
    report: dict[str, Any] = {
        "reference": str(ref_dir.relative_to(ROOT)),
        "reference_note": "Stage 1e pyannote 3.1 merged turns, not human gold",
        "frame_sec": FRAME,
        "systems": {},
    }
    for hyp in args.hyp_dir:
        hyp_dir = Path(hyp)
        name = hyp_dir.name
        clips = {}
        ders = []
        ious = []
        for clip_id, duration in CLIPS:
            ref = load_turns(ref_dir / f"{clip_id}.json")
            hyp_path = hyp_dir / f"{clip_id}.json"
            if not hyp_path.exists():
                clips[clip_id] = {"status": "missing"}
                continue
            row = score(ref, load_turns(hyp_path), duration)
            clips[clip_id] = row
            if row["collar_0_25"]["der"] is not None:
                ders.append(row["collar_0_25"]["der"])
            if row["raw"]["speech_iou"] is not None:
                ious.append(row["raw"]["speech_iou"])
        report["systems"][name] = {
            "hyp_dir": str(hyp_dir.relative_to(ROOT)),
            "mean_der_collar": round(sum(ders) / len(ders), 4) if ders else None,
            "mean_speech_iou": round(sum(ious) / len(ious), 4) if ious else None,
            "clips": clips,
        }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    for name, system in report["systems"].items():
        print(
            f"{name}: mean DER@0.25={system['mean_der_collar']}  "
            f"speech IoU={system['mean_speech_iou']}"
        )
        for clip_id, row in system["clips"].items():
            if "raw" not in row:
                print(f"  {clip_id}: missing")
                continue
            c = row["collar_0_25"]
            print(
                f"  {clip_id}: speakers {row['n_ref_speakers']}→{row['n_hyp_speakers']}  "
                f"turns {row['n_ref_turns']}→{row['n_hyp_turns']}  "
                f"DER={c['der']} miss={c['miss_sec']}s fa={c['false_alarm_sec']}s "
                f"conf={c['confusion_sec']}s  IoU={row['raw']['speech_iou']}"
            )


if __name__ == "__main__":
    main()

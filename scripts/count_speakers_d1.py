#!/usr/bin/env python3
"""Count unique speakers in results/d1 hyp vs research expectations.

Usage:
  python3 scripts/count_speakers_d1.py
  python3 scripts/count_speakers_d1.py --out eval/d1/1/speaker_count.md
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TURNS = ROOT / "results" / "d1" / "turns.json"
DEFAULT_TRANSCRIPT = ROOT / "results" / "d1" / "transcript.json"

# Research 1f/1f2 on the same meeting family (85 s clips): WeSpeaker ≈ 2/4/2/2
RESEARCH_CLIP_SPEAKERS = {
    "test_voice": 2,
    "test_apartments": 4,  # 1f vad_wespeaker; 1f2 reported 3 on silero+wespeaker family
    "test_transformers": 2,
    "test_ninth": 2,
}
EXPECTED_FULL_MEETING_MAX = 5  # human gate: >5 ⇒ diarization bug


def unique_speakers(path: Path, key_list: str) -> tuple[set[str], int]:
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data[key_list]
    speakers = {item["speaker"] for item in items}
    return speakers, int(data.get("speaker_count") or len(speakers))


def duration_by_speaker(turns_path: Path) -> Counter[str]:
    data = json.loads(turns_path.read_text(encoding="utf-8"))
    dur: Counter[str] = Counter()
    for t in data["turns"]:
        dur[t["speaker"]] += float(t["end"]) - float(t["start"])
    return dur


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--turns", type=Path, default=DEFAULT_TURNS)
    ap.add_argument("--transcript", type=Path, default=DEFAULT_TRANSCRIPT)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    t_sp, t_field = unique_speakers(args.turns, "turns")
    s_sp, _ = unique_speakers(args.transcript, "segments")
    dur = duration_by_speaker(args.turns)
    ids = sorted(int(s.split("_")[1]) for s in t_sp)
    tiny = sum(1 for d in dur.values() if d < 3.0)
    top5 = sum(d for _, d in dur.most_common(5)) / max(sum(dur.values()), 1e-9)

    n = len(t_sp)
    verdict = "OK" if n <= EXPECTED_FULL_MEETING_MAX else "FAIL_OVERSPLIT"

    lines = [
        "# D1 speaker count",
        "",
        f"- turns.json unique speakers: **{n}** (field `speaker_count`={t_field})",
        f"- transcript.json unique speakers: **{len(s_sp)}**",
        f"- label id range: `{ids[0]:02d}`…`{ids[-1]:02d}` (max id is **not** the count)",
        f"- speakers with total speech < 3 s: {tiny}/{n}",
        f"- top-5 speakers cover: {top5*100:.1f}% of diarized speech time",
        f"- gate vs expected ≤ {EXPECTED_FULL_MEETING_MAX}: **{verdict}**",
        "",
        "## Research reference (same meeting, ~85 s clips, WeSpeaker)",
        "",
    ]
    for clip, n_exp in RESEARCH_CLIP_SPEAKERS.items():
        lines.append(f"- {clip}: ~{n_exp} speakers in 1f/1f2")
    lines += [
        "",
        "Full-meeting hyp with **26** clusters is far above clip-scale 2–4 and above the",
        "human bar of 4–5. Treat as **diarization oversplit** — fix clustering before",
        "trusting speaker-aware eval.",
        "",
        "Likely causes to check in `src/transcriber/diarization/wespeaker.py`:",
        "- hardcoded `AgglomerativeClustering(distance_threshold=0.5)` on many windows",
        "  from a 24 min file (research tuned/used this on short clips, not full meeting)",
        "- no cap / no re-cluster after merge; sparse VAD → short embeds → extra clusters",
        "",
    ]

    text = "\n".join(lines)
    print(text)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Local D1 human-prep: cut gold windows, map speakers, write transcript_diff.md.

Does not read secrets. Gold stays under eval/; hyp under results/d1/.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD_DIR = ROOT / "eval" / "d1" / "transcribe"
VOICE_OUT = ROOT / "eval" / "d1" / "voice"
RESULTS = ROOT / "results" / "d1"
HYP_PATH = RESULTS / "transcript.json"
FULL_AUDIO = ROOT / "data" / "voice 002.m4a"
TEST_VOICE = ROOT / "data" / "test_voice.m4a"

# Checks / diffs live under eval/d1/{attempt}/ — results/d1 stays hyp-only
ATTEMPT = int(os.environ.get("EVAL_D1_ATTEMPT", "1"))
EVAL_ATTEMPT = ROOT / "eval" / "d1" / str(ATTEMPT)
DIFF_PATH = EVAL_ATTEMPT / "transcript_diff.md"

# Clip id → how to locate audio for cutting segment-relative times
CLIP_META = {
    "test_voice": {
        "audio": TEST_VOICE,
        "offset": 0.0,  # gold times already relative to this file
        "full_offset": 0.0,  # same window on full meeting (clip is meeting start)
    },
    "test_apartments": {
        "audio": FULL_AUDIO,
        "offset": 570.0,
        "full_offset": 570.0,
    },
    "test_transformers": {
        "audio": FULL_AUDIO,
        "offset": 875.0,
        "full_offset": 875.0,
    },
    "test_ninth": {
        "audio": FULL_AUDIO,
        "offset": 1245.0,
        "full_offset": 1245.0,
    },
}


def norm_text(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokens(s: str) -> list[str]:
    return [t for t in norm_text(s).split() if len(t) >= 2]


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def ffmpeg_cut(src: Path, start: float, end: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    dur = max(0.05, end - start)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{dur:.3f}",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(dest),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


@dataclass
class Pair:
    gold_id: int
    gold_speaker: str
    gold_text: str
    gold_start: float
    gold_end: float
    hyp_ids: list[str]
    hyp_speakers_raw: list[str]
    hyp_speakers_mapped: list[str]
    hyp_text: str
    status: str  # match | differ | missing_hyp | extra_note


def build_speaker_map(
    gold_segs: list[dict], hyp_segs: list[dict], *, tiou: float = 0.15
) -> dict[str, str]:
    """Map hyp SPEAKER_xx → gold SPEAKER_A/B/… by first overlapping text hit."""
    mapping: dict[str, str] = {}
    used_gold: set[str] = set()

    # Prefer chronological gold order: first solid token overlap wins
    for g in gold_segs:
        g_tok = set(tokens(g["text"]))
        if len(g_tok) < 2:
            continue
        best = None
        best_score = 0.0
        for h in hyp_segs:
            if h["speaker"] in mapping:
                continue
            ov = overlap(g["start"], g["end"], h["start"], h["end"])
            if ov <= 0 and abs(g["start"] - h["start"]) > 2.0:
                # allow near-miss by text only within ±2s start
                continue
            h_tok = set(tokens(h["text"]))
            if not h_tok:
                continue
            inter = len(g_tok & h_tok)
            if inter == 0:
                continue
            score = inter / max(1, len(g_tok))
            if ov > 0:
                score += 0.5 * (ov / max(0.01, g["end"] - g["start"]))
            if score > best_score:
                best_score = score
                best = h
        if best is not None and best_score >= 0.2:
            gsp = g["speaker"]
            if gsp not in used_gold:
                mapping[best["speaker"]] = gsp
                used_gold.add(gsp)

    # Remaining hyp speakers that only appear once with unique gold left — leave unmapped
    return mapping


def hyp_in_window(hyp: list[dict], t0: float, t1: float) -> list[dict]:
    out = []
    for h in hyp:
        if overlap(h["start"], h["end"], t0, t1) > 0:
            # shift to clip-relative times for comparison with gold
            out.append(
                {
                    **h,
                    "start": max(0.0, h["start"] - t0),
                    "end": max(0.0, h["end"] - t0),
                    "abs_start": h["start"],
                    "abs_end": h["end"],
                }
            )
    return out


def join_hyp_for_gold(
    g: dict, hyp_rel: list[dict], mapping: dict[str, str], collar: float
) -> tuple[list[dict], str]:
    hits = []
    for h in hyp_rel:
        if overlap(g["start"] - collar, g["end"] + collar, h["start"], h["end"]) > 0:
            hits.append(h)
    hits.sort(key=lambda x: x["start"])
    text = " ".join(h["text"].strip() for h in hits if h.get("text"))
    return hits, text


def text_similar(a: str, b: str) -> bool:
    ta, tb = set(tokens(a)), set(tokens(b))
    if not ta or not tb:
        return norm_text(a) == norm_text(b)
    inter = len(ta & tb)
    return inter / max(len(ta), len(tb)) >= 0.55 or inter / len(ta) >= 0.7


def process_clip(clip_id: str, gold: dict, hyp_full: list[dict]) -> dict:
    meta = CLIP_META[clip_id]
    offset = float(gold.get("source_start", meta["offset"]) or meta["offset"])
    duration = float(gold.get("duration_sec") or (gold.get("source_end", offset) - offset))
    t0, t1 = offset, offset + duration
    collar = float(gold.get("collar_sec", 0.25))

    # Audio source for segment cuts
    if clip_id == "test_voice":
        cut_src = TEST_VOICE
        cut_base = 0.0
        if not cut_src.is_file():
            cut_src = FULL_AUDIO
            cut_base = 0.0
    else:
        cut_src = FULL_AUDIO
        cut_base = offset

    hyp_rel = hyp_in_window(hyp_full, t0, t1)
    mapping = build_speaker_map(gold["segments"], hyp_rel)

    # Persist mapped hyp for this window
    mapped_hyp = []
    for h in hyp_rel:
        mapped_hyp.append(
            {
                "id": h["id"],
                "start": round(h["abs_start"], 3),
                "end": round(h["abs_end"], 3),
                "start_rel": round(h["start"], 3),
                "end_rel": round(h["end"], 3),
                "speaker_raw": h["speaker"],
                "speaker": mapping.get(h["speaker"], h["speaker"]),
                "text": h["text"],
            }
        )
    (EVAL_ATTEMPT / f"{clip_id}_hyp_mapped.json").write_text(
        json.dumps(
            {
                "clip": clip_id,
                "window_abs": [t0, t1],
                "speaker_map": mapping,
                "segments": mapped_hyp,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    # Cut per gold segment + whole window
    clip_voice = VOICE_OUT / clip_id
    clip_voice.mkdir(parents=True, exist_ok=True)
    if cut_src.is_file():
        ffmpeg_cut(cut_src, cut_base, cut_base + duration, clip_voice / f"{clip_id}_full.wav")
        for g in gold["segments"]:
            gs = cut_base + float(g["start"])
            ge = cut_base + float(g["end"])
            dest = clip_voice / f"seg{int(g['id']):02d}_{g['speaker']}.wav"
            ffmpeg_cut(cut_src, gs, ge, dest)

    pairs: list[Pair] = []
    for g in gold["segments"]:
        hits, hyp_text = join_hyp_for_gold(g, hyp_rel, mapping, collar)
        raw_sp = [h["speaker"] for h in hits]
        mapped_sp = [mapping.get(s, s) for s in raw_sp]
        if not hits:
            status = "missing_hyp"
        elif text_similar(g["text"], hyp_text) and (
            not mapped_sp or g["speaker"] in mapped_sp or not mapping
        ):
            status = "match"
        else:
            status = "differ"
        # speaker mismatch alone → differ
        if hits and mapping and g["speaker"] not in mapped_sp and hyp_text:
            if status == "match":
                status = "differ"
        pairs.append(
            Pair(
                gold_id=int(g["id"]),
                gold_speaker=g["speaker"],
                gold_text=g["text"],
                gold_start=float(g["start"]),
                gold_end=float(g["end"]),
                hyp_ids=[h["id"] for h in hits],
                hyp_speakers_raw=raw_sp,
                hyp_speakers_mapped=mapped_sp,
                hyp_text=hyp_text,
                status=status,
            )
        )

    return {
        "clip": clip_id,
        "status_gold": gold.get("status"),
        "window_abs": [t0, t1],
        "speaker_map": mapping,
        "pairs": pairs,
        "hyp_count": len(hyp_rel),
        "gold_count": len(gold["segments"]),
    }


def render_diff(reports: list[dict]) -> str:
    lines: list[str] = []
    lines.append(f"# D1 transcript diff — attempt {ATTEMPT}")
    lines.append("")
    lines.append("Hyp (core only): `results/d1/transcript.json` + `turns.json`.")
    lines.append("Gold: `eval/d1/transcribe/*.json`. Audio cuts: `eval/d1/voice/<clip>/`.")
    lines.append(f"This attempt folder: `eval/d1/{ATTEMPT}/`.")
    lines.append("")
    lines.append(
        "Auto speaker map is heuristic only — prefer human mapping when labels disagree."
    )
    lines.append("")

    for r in reports:
        lines.append(f"## {r['clip']} ({r['status_gold']})")
        lines.append("")
        lines.append(f"- Window on full meeting: `{r['window_abs'][0]:.1f}`–`{r['window_abs'][1]:.1f}` s")
        lines.append(f"- Gold segments: {r['gold_count']}, hyp overlapping: {r['hyp_count']}")
        sm = r["speaker_map"]
        if sm:
            lines.append("- Speaker map: " + ", ".join(f"`{k}`→`{v}`" for k, v in sorted(sm.items())))
        else:
            lines.append("- Speaker map: *(none — no confident first hit)*")
        n_match = sum(1 for p in r["pairs"] if p.status == "match")
        n_diff = sum(1 for p in r["pairs"] if p.status == "differ")
        n_miss = sum(1 for p in r["pairs"] if p.status == "missing_hyp")
        lines.append(f"- Counts: match={n_match}, differ={n_diff}, missing_hyp={n_miss}")
        lines.append("")

        diffs = [p for p in r["pairs"] if p.status != "match"]
        if not diffs:
            lines.append("_No differing pieces._")
            lines.append("")
            continue

        lines.append("### Differing / missing pieces")
        lines.append("")
        for p in diffs:
            lines.append(
                f"#### gold id={p.gold_id}  `{p.gold_start:.2f}`–`{p.gold_end:.2f}`  "
                f"**{p.gold_speaker}**  [{p.status}]"
            )
            lines.append("")
            lines.append(f"- **gold:** {p.gold_text}")
            if p.hyp_text:
                mapped = ", ".join(p.hyp_speakers_mapped) or "—"
                raw = ", ".join(p.hyp_speakers_raw) or "—"
                lines.append(
                    f"- **hyp** ({', '.join(p.hyp_ids)}; raw {raw} → mapped {mapped}): {p.hyp_text}"
                )
            else:
                lines.append("- **hyp:** *(no overlapping ASR segment)*")
            lines.append("")

    lines.append("## Human checklist")
    lines.append("")
    lines.append("1. Listen to `eval/d1/voice/<clip>/seg*.wav` for differ/missing rows.")
    lines.append("2. Confirm speaker map (especially `test_voice`: notes say A≈01, B≈03 on full).")
    lines.append("3. Record `HUMAN_GATE: PASS|FAIL` in `agent_docs/progress/stage_D1.md`.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    EVAL_ATTEMPT.mkdir(parents=True, exist_ok=True)
    VOICE_OUT.mkdir(parents=True, exist_ok=True)
    if not HYP_PATH.is_file():
        raise SystemExit(f"Missing hyp transcript: {HYP_PATH}")
    if not FULL_AUDIO.is_file() and not TEST_VOICE.is_file():
        raise SystemExit("Need data/voice 002.m4a and/or data/test_voice.m4a")

    hyp_doc = json.loads(HYP_PATH.read_text(encoding="utf-8"))
    hyp_full = hyp_doc["segments"]

    reports = []
    for path in sorted(GOLD_DIR.glob("*.json")):
        clip_id = path.stem
        if clip_id not in CLIP_META:
            continue
        gold = json.loads(path.read_text(encoding="utf-8"))
        print(f"processing {clip_id}…")
        reports.append(process_clip(clip_id, gold, hyp_full))

    DIFF_PATH.write_text(render_diff(reports), encoding="utf-8")
    summary = {
        "hyp": str(HYP_PATH.relative_to(ROOT)),
        "diff": str(DIFF_PATH.relative_to(ROOT)),
        "clips": [
            {
                "clip": r["clip"],
                "speaker_map": r["speaker_map"],
                "match": sum(1 for p in r["pairs"] if p.status == "match"),
                "differ": sum(1 for p in r["pairs"] if p.status == "differ"),
                "missing_hyp": sum(1 for p in r["pairs"] if p.status == "missing_hyp"),
            }
            for r in reports
        ],
    }
    (EVAL_ATTEMPT / "eval_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"attempt={ATTEMPT} wrote {DIFF_PATH}")


if __name__ == "__main__":
    main()

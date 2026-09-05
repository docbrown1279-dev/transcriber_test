#!/usr/bin/env python3
"""Run T2 Silero stack on 4 gold clips and write a readability-focused diff.

Priority: whole-window narrative vs gold joined text.
Per-segment missing pieces are listed but not treated as hard failures.

Writes:
  results/d1_parity_t2_gold/<clip>/
  eval/d1/5/transcript_diff.md
  eval/d1/5/summary.json
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "d1_parity_t2_gold"
EVAL = ROOT / "eval" / "d1" / "5"
GOLD_DIR = ROOT / "eval" / "d1" / "transcribe"
VOICE = ROOT / "eval" / "d1" / "voice"

CLIPS = [
    "test_voice",
    "test_apartments",
    "test_transformers",
    "test_ninth",
]


def apply_t2(cfg):  # noqa: ANN001
    """Parity 1f VAD + soft T2 merge/silence (no dynaudnorm)."""
    cfg.audio.vad_preprocess.enabled = False
    cfg.audio.asr_per_turn_gain = True
    cfg.vad.engine = "silero"
    cfg.vad.threshold = 0.45
    cfg.vad.neg_threshold = 0.30
    cfg.vad.min_speech_ms = 200
    cfg.vad.min_silence_ms = 350
    cfg.vad.fallback = "disabled"
    cfg.diarization.merge.same_speaker_gap_sec = 0.3
    cfg.diarization.merge.absorb_turn_shorter_than_sec = 1.0
    cfg.diarization.merge.vad_premerge_gap_sec = 0.5
    cfg.diarization.merge.min_hole_sec = 0.5
    return cfg


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]+", " ", s, flags=re.UNICODE)
    return re.sub(r"\s+", " ", s).strip()


def tokens(s: str) -> set[str]:
    return {t for t in norm(s).split() if len(t) >= 2}


def token_recall(gold: str, hyp: str) -> float:
    g, h = tokens(gold), tokens(hyp)
    if not g:
        return 1.0 if not h else 0.0
    return len(g & h) / len(g)


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def segs_from_artifact(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for s in data.get("segments") or []:
        text = (s.get("text") or "").strip()
        if not text:
            continue
        rows.append(
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "speaker": s.get("speaker"),
                "text": text,
                "id": s.get("id"),
            }
        )
    return rows


def join_window(rows: list[dict], t0: float = 0.0, t1: float = 1e9) -> str:
    parts = [
        r["text"]
        for r in rows
        if overlap(r["start"], r["end"], t0, t1) > 0.05
    ]
    return " ".join(parts)


def hyp_for_gold(g: dict, hyp: list[dict], pad: float = 2.0) -> str:
    hits = [
        h
        for h in hyp
        if overlap(g["start"] - pad, g["end"] + pad, h["start"], h["end"]) > 0
    ]
    hits.sort(key=lambda x: x["start"])
    return " ".join(h["text"] for h in hits)


def run_clips() -> None:
    from transcriber.config.loader import load_config
    from transcriber.pipeline.orchestrator import run_job

    OUT.mkdir(parents=True, exist_ok=True)
    for clip in CLIPS:
        audio = VOICE / clip / f"{clip}_full.wav"
        if not audio.is_file():
            print(f"SKIP missing {audio}", flush=True)
            continue
        job = OUT / clip
        if job.exists():
            shutil.rmtree(job)
        job.mkdir(parents=True)
        print(f"=== T2 {clip} ===", flush=True)
        cfg = apply_t2(load_config("demo"))
        run_job(job_dir=job, source_audio=audio, until="correction_suggest", cfg=cfg)
        speech = json.loads((job / "speech.json").read_text(encoding="utf-8"))
        tr = json.loads((job / "transcript.json").read_text(encoding="utf-8"))
        n = sum(1 for s in tr.get("segments") or [] if (s.get("text") or "").strip())
        print(f"  speech={speech.get('speech_sec')} nonempty={n}", flush=True)


def write_diff() -> None:
    EVAL.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        "# D1 transcript diff — attempt 5 (T2 Silero parity)",
        "",
        "Stack: snakers4 Silero + context, **no dynaudnorm**, thr=0.45, "
        "`min_silence_ms=350`, `vad_premerge_gap=0.5`, merge mild (0.3/1.0), GigaAM v3.",
        "",
        "Hyp: `results/d1_parity_t2_gold/<clip>/`. Gold: `eval/d1/transcribe/`.",
        "",
        "Judgement focus: **whole-window readability** (token recall of joined gold). "
        "Missing single gold crumbs are secondary.",
        "",
        "| clip | gold segs | hyp nonempty | window token-recall | missing_hyp | differ | match-ish |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    summary: list[dict] = []

    for clip in CLIPS:
        gold_path = GOLD_DIR / f"{clip}.json"
        hyp_path = OUT / clip / "transcript.json"
        if not gold_path.is_file() or not hyp_path.is_file():
            lines.append(f"| `{clip}` | — | — | — | SKIP |")
            continue
        gold = json.loads(gold_path.read_text(encoding="utf-8"))
        g_segs = gold.get("segments") or []
        hyp = segs_from_artifact(hyp_path)
        gold_joined = " ".join((g.get("text") or "").strip() for g in g_segs)
        hyp_joined = join_window(hyp)
        recall = token_recall(gold_joined, hyp_joined)

        missing = differ = matchish = 0
        pairs = []
        for g in g_segs:
            ht = hyp_for_gold(g, hyp)
            if not ht.strip():
                status = "missing_hyp"
                missing += 1
            elif token_recall(g.get("text") or "", ht) >= 0.55:
                status = "matchish"
                matchish += 1
            else:
                status = "differ"
                differ += 1
            pairs.append(
                {
                    "id": g.get("id"),
                    "start": g.get("start"),
                    "end": g.get("end"),
                    "speaker": g.get("speaker"),
                    "status": status,
                    "gold": (g.get("text") or "").strip(),
                    "hyp": ht.strip(),
                    "recall": round(token_recall(g.get("text") or "", ht), 3),
                }
            )

        row = {
            "clip": clip,
            "n_gold": len(g_segs),
            "n_hyp": len(hyp),
            "window_token_recall": round(recall, 3),
            "missing_hyp": missing,
            "differ": differ,
            "matchish": matchish,
            "gold_joined": gold_joined,
            "hyp_joined": hyp_joined,
            "pairs": pairs,
        }
        summary.append(row)
        lines.append(
            f"| `{clip}` | {len(g_segs)} | {len(hyp)} | **{recall:.2f}** | "
            f"{missing} | {differ} | {matchish} |"
        )

        (EVAL / f"{clip}_compare.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    lines += ["", "## Per-clip narrative (gold vs hyp joined)", ""]
    for row in summary:
        lines += [
            f"### {row['clip']}  (window token-recall **{row['window_token_recall']:.2f}**)",
            "",
            f"- Gold segs: {row['n_gold']}, hyp nonempty: {row['n_hyp']}, "
            f"matchish={row['matchish']}, differ={row['differ']}, missing={row['missing_hyp']}",
            "",
            "**gold (joined):**",
            "",
            row["gold_joined"],
            "",
            "**hyp (joined):**",
            "",
            row["hyp_joined"],
            "",
            "<details><summary>Per-segment (differ / missing only)</summary>",
            "",
        ]
        for p in row["pairs"]:
            if p["status"] == "matchish":
                continue
            lines += [
                f"#### gold id={p['id']}  `{p['start']}`–`{p['end']}`  "
                f"**{p['speaker']}**  [{p['status']}] recall={p['recall']}",
                "",
                f"- **gold:** {p['gold']}",
                f"- **hyp:** {p['hyp'] or '∅'}",
                "",
            ]
        lines += ["</details>", ""]

    lines += [
        "## How to read",
        "",
        "1. Prefer window token-recall and the joined narrative blocks.",
        "2. `missing_hyp` on short gold crumbs is OK if the surrounding sentence is intact.",
        "3. Compare mentally to attempt 4 (`eval/d1/4/`) which used C3+agg on full meeting.",
        "",
    ]

    (EVAL / "transcript_diff.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (EVAL / "summary.json").write_text(
        json.dumps(
            [
                {
                    "clip": r["clip"],
                    "window_token_recall": r["window_token_recall"],
                    "missing_hyp": r["missing_hyp"],
                    "differ": r["differ"],
                    "matchish": r["matchish"],
                    "n_gold": r["n_gold"],
                    "n_hyp": r["n_hyp"],
                }
                for r in summary
            ],
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {EVAL / 'transcript_diff.md'}", flush=True)
    for r in summary:
        print(
            f"  {r['clip']}: recall={r['window_token_recall']:.2f} "
            f"miss={r['missing_hyp']} differ={r['differ']} matchish={r['matchish']}",
            flush=True,
        )


def main() -> int:
    only = sys.argv[1:]
    if only == ["diff"]:
        write_diff()
        return 0
    run_clips()
    write_diff()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

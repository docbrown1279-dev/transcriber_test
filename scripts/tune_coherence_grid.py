#!/usr/bin/env python3
"""Compress × merge A/B on the 10 d1 windows (full normalize→…→ASR).

Diarization already reads normalized.wav (gain, no compressor); only Silero
uses vad_input. This grid varies VAD preprocess + turn-merge knobs.

Writes eval/d1/partial_coherence_grid/ and agent_docs/reports/d1_coherence_grid.md.
"""

from __future__ import annotations

import json
import shutil
import statistics
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tune_silero_vad import WINDOWS, VOICE, extract_wav  # noqa: E402

from transcriber.config.loader import load_config  # noqa: E402
from transcriber.models.artifacts import TranscriptArtifact, load_artifact  # noqa: E402
from transcriber.pipeline.orchestrator import run_job  # noqa: E402

OUT = ROOT / "eval" / "d1" / "partial_coherence_grid"
REPORT = ROOT / "agent_docs" / "reports" / "d1_coherence_grid.md"


@dataclass(frozen=True)
class CompressPreset:
    id: str
    ffmpeg_af: str | None
    note: str


@dataclass(frozen=True)
class MergePreset:
    id: str
    same_speaker_gap_sec: float
    absorb_turn_shorter_than_sec: float
    vad_premerge_gap_sec: float
    note: str


COMPRESS: list[CompressPreset] = [
    CompressPreset(
        "C1",
        "acompressor=threshold=0.031622776:ratio=4:attack=20:release=200:"
        "makeup=4:knee=2.828:detection=rms",
        "light acompressor (eval C1)",
    ),
    CompressPreset(
        "C3",
        "dynaudnorm=f=150:g=7:p=0.9",
        "current dual-path dynaudnorm",
    ),
    CompressPreset(
        "C3s",
        "dynaudnorm=f=250:g=5:p=0.9",
        "softer dynaudnorm (slower/less gain)",
    ),
]

MERGE: list[MergePreset] = [
    MergePreset("mild", 0.5, 1.5, 0.8, "gentler glue"),
    MergePreset("n2", 0.6, 2.0, 0.8, "current coherence N2"),
    MergePreset("agg", 0.8, 2.5, 1.0, "aggressive glue"),
]


def _dur_median(items: list[dict]) -> float | None:
    if not items:
        return None
    durs = [float(x["end"]) - float(x["start"]) for x in items]
    return round(statistics.median(durs), 3)


def _speaker_switches(turns: list[dict]) -> int:
    if len(turns) < 2:
        return 0
    return sum(
        1
        for a, b in zip(turns, turns[1:])
        if a.get("speaker") != b.get("speaker")
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []

    for comp in COMPRESS:
        for merge in MERGE:
            vid = f"{comp.id}_{merge.id}"
            print(f"\n=== variant {vid} ===", flush=True)
            for i, win in enumerate(WINDOWS, start=1):
                print(f"  [{i}/{len(WINDOWS)}] {win.name} …", flush=True)
                job_dir = OUT / "jobs" / vid / win.name
                if job_dir.exists():
                    shutil.rmtree(job_dir)
                job_dir.mkdir(parents=True)
                wav = job_dir / "window.wav"
                src = VOICE / win.clip / f"{win.clip}_full.wav"
                extract_wav(src, win.start, win.end, wav)

                cfg = load_config("demo")
                cfg.audio.vad_preprocess.enabled = comp.ffmpeg_af is not None
                cfg.audio.vad_preprocess.ffmpeg_af = (
                    comp.ffmpeg_af or "dynaudnorm=f=150:g=7:p=0.9"
                )
                if comp.ffmpeg_af is None:
                    cfg.audio.vad_preprocess.enabled = False
                cfg.vad.min_speech_ms = 400
                cfg.diarization.merge.same_speaker_gap_sec = merge.same_speaker_gap_sec
                cfg.diarization.merge.absorb_turn_shorter_than_sec = (
                    merge.absorb_turn_shorter_than_sec
                )
                cfg.diarization.merge.vad_premerge_gap_sec = merge.vad_premerge_gap_sec

                run_job(
                    job_dir=job_dir,
                    source_audio=wav,
                    until="correction_suggest",
                    cfg=cfg,
                )

                speech = json.loads((job_dir / "speech.json").read_text(encoding="utf-8"))
                turns = json.loads((job_dir / "turns.json").read_text(encoding="utf-8"))
                tr = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
                turn_list = turns.get("turns") or []
                segs = [s for s in tr.segments if (s.text or "").strip()]
                texts = [s.text.strip() for s in segs]
                le3 = sum(1 for t in texts if len(t.split()) <= 3)
                win_dur = win.end - win.start
                cover = float(speech.get("speech_sec") or 0.0) / win_dur if win_dur else 0.0

                rows.append(
                    {
                        "variant": vid,
                        "compress": comp.id,
                        "merge": merge.id,
                        "kind": win.kind,
                        "window": win.name,
                        "cover": round(cover, 4),
                        "speech_sec": float(speech.get("speech_sec") or 0.0),
                        "n_regions": len(speech.get("regions") or []),
                        "n_turns": len(turn_list),
                        "median_turn": _dur_median(turn_list),
                        "speaker_count": turns.get("speaker_count"),
                        "speaker_switches": _speaker_switches(turn_list),
                        "n_asr": len(tr.segments),
                        "nonempty": len(segs),
                        "le3_words": le3,
                        "hyp": " | ".join(texts),
                    }
                )

    (OUT / "grid_rows.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Aggregate per variant
    by_var: dict[str, list[dict]] = {}
    for r in rows:
        by_var.setdefault(r["variant"], []).append(r)

    lines = [
        "# Coherence grid — compress × merge (10 windows)",
        "",
        "Full chain per window. **VAD** = `vad_input` (compress). "
        "**Diarization + ASR** = `normalized.wav` (linear gain, no compressor); "
        "ASR also applies per-turn gain on slices.",
        "",
        "## Architecture (unchanged)",
        "",
        "| stage | wav | notes |",
        "|---|---|---|",
        "| Silero VAD | `vad_input.wav` | only path that gets compressor/dynaudnorm |",
        "| WeSpeaker | `normalized.wav` | same as ASR base; **not** compressed |",
        "| GigaAM | `normalized.wav` + per-turn gain | compressor never on ASR |",
        "",
        "VAD and diarization are **separate stages**: VAD supplies speech regions; "
        "diarization embeds those intervals from the clean wav. No need to feed "
        "compressed audio to WeSpeaker — already clean.",
        "",
        "## Presets",
        "",
        "### Compress (VAD only)",
        "",
        "| id | ffmpeg `-af` |",
        "|---|---|",
    ]
    for c in COMPRESS:
        lines.append(f"| `{c.id}` | `{c.ffmpeg_af}` — {c.note} |")
    lines += [
        "",
        "### Merge",
        "",
        "| id | same_speaker_gap | absorb | premerge |",
        "|---|---:|---:|---:|",
    ]
    for m in MERGE:
        lines.append(
            f"| `{m.id}` | {m.same_speaker_gap_sec} | "
            f"{m.absorb_turn_shorter_than_sec} | {m.vad_premerge_gap_sec} |"
        )

    lines += [
        "",
        "## Summary by variant (mean over 10 windows)",
        "",
        "| variant | cover | n_reg | n_turns | med_turn | speakers | switches | le3 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]

    summary_rows: list[tuple[str, dict]] = []
    for vid, rs in sorted(by_var.items()):
        agg = {
            "cover": round(statistics.mean(r["cover"] for r in rs), 3),
            "n_reg": round(statistics.mean(r["n_regions"] for r in rs), 1),
            "n_turns": round(statistics.mean(r["n_turns"] for r in rs), 1),
            "med_turn": round(
                statistics.mean(r["median_turn"] or 0 for r in rs), 2
            ),
            "speakers": round(statistics.mean(float(r["speaker_count"] or 0) for r in rs), 2),
            "switches": round(statistics.mean(r["speaker_switches"] for r in rs), 1),
            "le3": round(statistics.mean(r["le3_words"] for r in rs), 1),
            "rescue_cover": round(
                statistics.mean(r["cover"] for r in rs if r["kind"] == "rescue"), 3
            ),
            "regr_cover": round(
                statistics.mean(r["cover"] for r in rs if r["kind"] == "regression"), 3
            ),
        }
        summary_rows.append((vid, agg))
        lines.append(
            f"| `{vid}` | {agg['cover']:.3f} | {agg['n_reg']} | {agg['n_turns']} | "
            f"{agg['med_turn']} | {agg['speakers']} | {agg['switches']} | {agg['le3']} |"
        )

    lines += [
        "",
        "### Rescue vs regression cover",
        "",
        "| variant | rescue_cover | regression_cover |",
        "|---|---:|---:|",
    ]
    for vid, agg in summary_rows:
        lines.append(f"| `{vid}` | {agg['rescue_cover']:.3f} | {agg['regr_cover']:.3f} |")

    lines += [
        "",
        "## Per-window hyp (selected variants)",
        "",
    ]
    # show C1_n2, C3_n2, C3s_mild hyp for rescue windows
    show = {"C1_n2", "C3_n2", "C3s_mild", "C1_mild", "C3_agg"}
    for win in WINDOWS:
        if win.kind != "rescue":
            continue
        lines.append(f"### {win.name}")
        lines.append("")
        for r in rows:
            if r["window"] == win.name and r["variant"] in show:
                lines.append(f"- **{r['variant']}** (le3={r['le3_words']}): {r['hyp'][:240]}")
        lines.append("")

    lines += [
        "## Auto notes",
        "",
        "- Prefer higher rescue_cover without collapsing speaker_switches to ~0 on multi-speaker windows.",
        "- Prefer lower le3 and higher med_turn for coherence.",
        "- Soft C3s may trade some cover for fewer crumbs before merge.",
        "",
    ]

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {OUT / 'grid_rows.json'}")
    print(f"Wrote {REPORT}")


if __name__ == "__main__":
    main()

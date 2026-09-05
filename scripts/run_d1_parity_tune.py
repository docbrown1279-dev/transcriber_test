#!/usr/bin/env python3
"""Soft tunes after 1f Silero parity (T0/T1/T2) on test_voice only.

T0 = parity baseline (no vad preprocess, thr 0.45 / min_silence 50, merge mild)
T1 = peak-only alimiter on vad_input (no dynaudnorm)
T2 = T0 + min_silence_ms=350 + vad_premerge_gap=0.5

Writes results/d1_parity_tune/ and appends notes to the parity report.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "d1_parity_tune"
AUDIO = ROOT / "data" / "test_voice.m4a"
REF = ROOT / "data" / "research_asr_1f_vad_wespeaker" / "test_voice.json"
REPORT = ROOT / "agent_docs" / "reports" / "d1_silero_parity.md"


def segments_to_rows(segments) -> list[dict]:  # noqa: ANN001
    rows = []
    for s in segments:
        if isinstance(s, dict):
            text = (s.get("text") or "").strip()
            start = float(s.get("start", 0))
            end = float(s.get("end", 0))
            speaker = s.get("speaker")
        else:
            text = (getattr(s, "text", None) or "").strip()
            start = float(s.start)
            end = float(s.end)
            speaker = getattr(s, "speaker", None)
        if text:
            rows.append({"start": start, "end": end, "speaker": speaker, "text": text})
    return rows


def text_0_75(rows: list[dict]) -> str:
    return " | ".join(r["text"] for r in rows if r["end"] > 0 and r["start"] < 75)


def apply_base_1f(cfg):  # noqa: ANN001
    cfg.audio.asr_per_turn_gain = True
    cfg.vad.engine = "silero"
    cfg.vad.threshold = 0.45
    cfg.vad.neg_threshold = 0.30
    cfg.vad.min_speech_ms = 200
    cfg.vad.min_silence_ms = 50
    cfg.vad.fallback = "disabled"
    cfg.diarization.merge.same_speaker_gap_sec = 0.3
    cfg.diarization.merge.absorb_turn_shorter_than_sec = 1.0
    cfg.diarization.merge.vad_premerge_gap_sec = 0.3
    cfg.diarization.merge.min_hole_sec = 0.5
    return cfg


def variant_cfg(vid: str):  # noqa: ANN001
    from transcriber.config.loader import load_config

    cfg = apply_base_1f(load_config("demo"))
    if vid == "T0":
        cfg.audio.vad_preprocess.enabled = False
    elif vid == "T1":
        # Peak ceiling only — do not reshape loudness envelope like dynaudnorm.
        cfg.audio.vad_preprocess.enabled = True
        cfg.audio.vad_preprocess.ffmpeg_af = "alimiter=limit=-1dB:level=false"
    elif vid == "T2":
        cfg.audio.vad_preprocess.enabled = False
        cfg.vad.min_silence_ms = 350
        cfg.diarization.merge.vad_premerge_gap_sec = 0.5
    else:
        raise ValueError(vid)
    return cfg


def main() -> int:
    from transcriber.models.artifacts import TranscriptArtifact, load_artifact
    from transcriber.pipeline.orchestrator import run_job

    OUT.mkdir(parents=True, exist_ok=True)
    ref_rows = segments_to_rows(json.loads(REF.read_text()).get("segments") or [])
    summary: list[dict] = []

    for vid in ("T0", "T1", "T2"):
        print(f"=== {vid} ===", flush=True)
        job = OUT / vid
        if job.exists():
            shutil.rmtree(job)
        job.mkdir(parents=True)
        cfg = variant_cfg(vid)
        run_job(job_dir=job, source_audio=AUDIO, until="correction_suggest", cfg=cfg)
        tr = load_artifact(job / "transcript.json", TranscriptArtifact)
        audio = json.loads((job / "audio.json").read_text(encoding="utf-8"))
        speech = json.loads((job / "speech.json").read_text(encoding="utf-8"))
        turns = json.loads((job / "turns.json").read_text(encoding="utf-8"))
        hyp = segments_to_rows(tr.segments)
        # Focus phrases for human gate
        canal = " | ".join(
            r["text"]
            for r in hyp
            if 25 <= r["start"] < 36 and r["text"]
        )
        expert = " | ".join(
            r["text"]
            for r in hyp
            if 35 <= r["start"] < 52 and r["text"]
        )
        row = {
            "id": vid,
            "vad_applied": (audio.get("vad_input") or {}).get("applied"),
            "vad_filter": (audio.get("vad_input") or {}).get("filter"),
            "speech_sec": speech.get("speech_sec"),
            "n_regions": len(speech.get("regions") or []),
            "n_turns": len(turns.get("turns") or []),
            "n_nonempty": len(hyp),
            "canalization_25_36": canal,
            "expertise_35_52": expert,
            "hyp_0_75": text_0_75(hyp),
            "ref_0_75": text_0_75(ref_rows),
            "runtime_asr_sec": tr.runtime_sec,
        }
        summary.append(row)
        (job / "tune_compare.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"  speech={row['speech_sec']:.1f} turns={row['n_turns']} "
            f"canal={canal!r}",
            flush=True,
        )

    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "",
        "## Soft tunes (T0/T1/T2) — test_voice",
        "",
        "| id | vad_pp | speech_sec | turns | canalization 25–36 | expertise 35–52 |",
        "|---|---|---:|---:|---|---|",
    ]
    for r in summary:
        lines.append(
            f"| `{r['id']}` | {r['vad_filter'] or 'off'} | {r['speech_sec']:.1f} | "
            f"{r['n_turns']} | {r['canalization_25_36'][:80]} | "
            f"{r['expertise_35_52'][:80]} |"
        )
    lines += [
        "",
        "Artifacts: `results/d1_parity_tune/`.",
        "",
    ]
    with REPORT.open("a", encoding="utf-8") as fh:
        fh.write("\n".join(lines))
    print(f"Appended tune table to {REPORT}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

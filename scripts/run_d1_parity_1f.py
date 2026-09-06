#!/usr/bin/env python3
"""Reproduce Stage 1f Silero+WeSpeaker on eval clips (no dynaudnorm).

Ticket: agent_docs/plans/ticket_d1_silero_parity.md
Writes results/d1_parity_1f/<clip>/ and a short compare summary JSON.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "d1_parity_1f"
REF_DIR = ROOT / "data" / "research_asr_1f_vad_wespeaker"

CLIPS: list[tuple[str, Path]] = [
    ("test_voice", ROOT / "data" / "test_voice.m4a"),
    ("test_apartments", ROOT / "eval" / "d1" / "voice" / "test_apartments" / "test_apartments_full.wav"),
    ("test_transformers", ROOT / "eval" / "d1" / "voice" / "test_transformers" / "test_transformers_full.wav"),
    ("test_ninth", ROOT / "eval" / "d1" / "voice" / "test_ninth" / "test_ninth_full.wav"),
]


def apply_1f_overrides(cfg):  # noqa: ANN001
    """Match research 1f vad_wespeaker stack (raw VAD + mild merge).

    Note: Stage 1f used threshold=0.45 and min_silence_ms=50 (see
    scripts/run_stage1f.py speech_timestamps), not the ticket's 0.5/200 sketch.
    """
    cfg.audio.vad_preprocess.enabled = False
    cfg.audio.asr_per_turn_gain = True
    cfg.vad.engine = "silero"
    cfg.vad.threshold = 0.45
    cfg.vad.neg_threshold = 0.30  # max(threshold - 0.15, 0.01) as in 1f
    cfg.vad.min_speech_ms = 200
    cfg.vad.min_silence_ms = 50
    cfg.vad.fallback = "disabled"
    cfg.diarization.merge.same_speaker_gap_sec = 0.3
    cfg.diarization.merge.absorb_turn_shorter_than_sec = 1.0
    cfg.diarization.merge.vad_premerge_gap_sec = 0.3
    cfg.diarization.merge.min_hole_sec = 0.5
    return cfg


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
        if not text:
            continue
        rows.append({"start": start, "end": end, "speaker": speaker, "text": text})
    return rows


def text_0_75(rows: list[dict]) -> str:
    parts = []
    for r in rows:
        if r["end"] <= 0 or r["start"] >= 75:
            continue
        parts.append(r["text"])
    return " | ".join(parts)


def main() -> int:
    sys.path.insert(0, str(ROOT / "src"))
    from transcriber.config.loader import load_config
    from transcriber.models.artifacts import TranscriptArtifact, load_artifact
    from transcriber.pipeline.orchestrator import run_job

    OUT.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []

    only = sys.argv[1:]  # optional clip ids
    clips = CLIPS
    if only:
        clips = [c for c in CLIPS if c[0] in only]

    for clip_id, audio in clips:
        if not audio.is_file():
            print(f"SKIP {clip_id}: missing {audio}", flush=True)
            summary.append({"clip": clip_id, "status": "missing_audio", "path": str(audio)})
            continue

        job_dir = OUT / clip_id
        if job_dir.exists():
            shutil.rmtree(job_dir)
        job_dir.mkdir(parents=True)

        print(f"=== {clip_id} ({audio}) ===", flush=True)
        cfg = apply_1f_overrides(load_config("demo"))
        run_job(
            job_dir=job_dir,
            source_audio=audio,
            until="correction_suggest",
            cfg=cfg,
        )

        tr = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
        audio_art = json.loads((job_dir / "audio.json").read_text(encoding="utf-8"))
        speech = json.loads((job_dir / "speech.json").read_text(encoding="utf-8"))
        turns = json.loads((job_dir / "turns.json").read_text(encoding="utf-8"))
        hyp_rows = segments_to_rows(tr.segments)

        ref_path = REF_DIR / f"{clip_id}.json"
        ref_rows: list[dict] = []
        if ref_path.is_file():
            ref = json.loads(ref_path.read_text(encoding="utf-8"))
            ref_rows = segments_to_rows(ref.get("segments") or ref.get("turns") or [])

        row = {
            "clip": clip_id,
            "status": "ok",
            "vad_applied": (audio_art.get("vad_input") or {}).get("applied"),
            "vad_filter": (audio_art.get("vad_input") or {}).get("filter"),
            "speech_sec": speech.get("speech_sec"),
            "n_regions": len(speech.get("regions") or []),
            "n_speakers": turns.get("n_speakers"),
            "n_turns": len(turns.get("turns") or []),
            "n_asr_segments": len(tr.segments),
            "n_nonempty": len(hyp_rows),
            "hyp_0_75": text_0_75(hyp_rows),
            "ref_0_75": text_0_75(ref_rows) if ref_rows else None,
            "ref_n_turns": len(ref_rows) if ref_rows else None,
            "runtime_asr_sec": tr.runtime_sec,
        }
        summary.append(row)
        (job_dir / "parity_compare.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"  vad_applied={row['vad_applied']} speakers={row['n_speakers']} "
            f"turns={row['n_turns']} nonempty={row['n_nonempty']}",
            flush=True,
        )
        print(f"  hyp_0_75[:120]={row['hyp_0_75'][:120]!r}", flush=True)

    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Wrote {OUT / 'summary.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

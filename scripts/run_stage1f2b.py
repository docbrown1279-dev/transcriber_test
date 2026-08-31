#!/usr/bin/env python3
"""Stage 1f2b: GigaAM v3 on frozen TEN-VAD and FSMN-VAD speech regions.

Does not recompute VAD. Does not write into ten_vad/ or fsmn_vad/.
ASR recipe matches Stage 1f: prepare_gain_rows / extract_clip / v3_rnnt CPU.
"""

from __future__ import annotations

import os

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")

import argparse
import gc
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_stage1e import SAMPLE_RATE, holes  # noqa: E402
from run_stage1f import (  # noqa: E402
    CLIPS,
    extract_clip,
    peak_rss_mb,
    prepare_gain_rows,
    write_json,
)

OUT = ROOT / "results" / "asr" / "1f2"
REPORTS = ROOT / "results" / "reports" / "1f2"
EXTRACTS = OUT / "_extracts"
NUM_THREADS = 2
MIN_TRANSCRIBE_SEC = 0.08

JOBS: dict[str, dict[str, str]] = {
    "gigaam_ten": {
        "vad_id": "ten_vad",
        "source_dir": "results/asr/1f2/ten_vad",
    },
    "gigaam_fsmn": {
        "vad_id": "fsmn_vad",
        "source_dir": "results/asr/1f2/fsmn_vad",
    },
}


def fail(kind: str, **extra: Any) -> None:
    payload = {"failure_kind": kind, **extra}
    write_json(REPORTS / "failure.json", payload)
    raise SystemExit(f"failure_kind: {kind}")


def require_clips_and_regions() -> None:
    missing_clips = [str(path.relative_to(ROOT)) for _, path, _ in CLIPS if not path.is_file()]
    if missing_clips:
        fail("missing_fixture", missing=missing_clips)
    missing_vad: list[str] = []
    for job in JOBS.values():
        source_dir = ROOT / job["source_dir"]
        for clip_id, _, _ in CLIPS:
            path = source_dir / f"{clip_id}.json"
            if not path.is_file():
                missing_vad.append(str(path.relative_to(ROOT)))
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            if "speech_regions" not in payload:
                missing_vad.append(str(path.relative_to(ROOT)) + "#speech_regions")
    if missing_vad:
        fail("missing_baseline", missing=missing_vad)


def regions_as_turns(regions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for region in regions:
        rows.append(
            {
                "start": float(region["start"]),
                "end": float(region["end"]),
                "speaker": "SPEECH",
            }
        )
    return rows


def transcribe_wav(model: Any, wav: Path) -> str:
    try:
        return str(model.transcribe(str(wav))).strip()
    except Exception:
        return ""


def run_job(job_id: str) -> None:
    require_clips_and_regions()
    spec = JOBS[job_id]
    source_dir = ROOT / spec["source_dir"]
    dest_dir = OUT / job_id
    dest_dir.mkdir(parents=True, exist_ok=True)

    import torch

    torch.set_num_threads(NUM_THREADS)
    import gigaam

    model = gigaam.load_model("v3_rnnt", fp16_encoder=False, device="cpu")
    started = time.monotonic()
    empty_total = 0
    clip_runtimes: dict[str, float] = {}

    for clip_id, audio, duration in CLIPS:
        dest_path = dest_dir / f"{clip_id}.json"
        if dest_path.is_file():
            existing = json.loads(dest_path.read_text(encoding="utf-8"))
            if existing.get("segments"):
                empty_total += int(existing.get("empty_segment_count") or 0)
                clip_runtimes[clip_id] = float(existing.get("asr_runtime_sec") or 0.0)
                continue

        source_path = source_dir / f"{clip_id}.json"
        source = json.loads(source_path.read_text(encoding="utf-8"))
        speech_regions = source["speech_regions"]
        merged = regions_as_turns(speech_regions)
        extract_dir = EXTRACTS / job_id / clip_id
        extract_dir.mkdir(parents=True, exist_ok=True)

        clip_started = time.monotonic()
        rows = prepare_gain_rows(clip_id, audio, merged, extract_dir, duration)
        pieces: list[dict[str, Any]] = []
        import soundfile as sf

        max_samples = 25 * SAMPLE_RATE
        for row in rows:
            piece_start = float(row["start"])
            piece_number = 0
            while piece_start < float(row["end"]) - 1e-9:
                piece_end = min(piece_start + 25.0, float(row["end"]))
                wav = extract_dir / f"turn_{row['id']:03d}_piece_{piece_number:02d}_linear.wav"
                extract_clip(audio, piece_start, piece_end, wav, duration, float(row["gain_db"]))
                text = ""
                if piece_end - piece_start >= MIN_TRANSCRIBE_SEC and wav.is_file():
                    data, rate = sf.read(wav)
                    if len(data) > max_samples:
                        sf.write(wav, data[:max_samples], rate)
                    if len(data) > 0:
                        text = transcribe_wav(model, wav)
                pieces.append(
                    {
                        "id": len(pieces),
                        "start": round(piece_start, 6),
                        "end": round(piece_end, 6),
                        "speaker": "SPEECH",
                        "text": text,
                    }
                )
                piece_start = piece_end
                piece_number += 1

        empty_count = sum(1 for piece in pieces if not piece["text"])
        empty_total += empty_count
        asr_runtime = round(time.monotonic() - clip_started, 3)
        clip_runtimes[clip_id] = asr_runtime
        payload = {
            "audio": str(audio.relative_to(ROOT)),
            "language": "ru",
            "duration_sec": duration,
            "asr_id": job_id,
            "vad_id": spec["vad_id"],
            "source_regions": str(source_path.relative_to(ROOT)),
            "model": "gigaam-v3-rnnt",
            "provider": "gigaam",
            "execution_mode": "local",
            "torch": True,
            "n_speakers": 1,
            "n_turns": len(rows),
            "speech_regions": speech_regions,
            "merged_turns": rows,
            "holes_ge_0_5_sec": holes(rows, duration),
            "asr_model": "gigaam-v3-rnnt",
            "asr_provider": "gigaam",
            "asr_runtime_sec": asr_runtime,
            "peak_rss_mb": peak_rss_mb(),
            "gain": "linear" if any(float(row["gain_db"]) > 0 for row in rows) else "none",
            "segments": pieces,
            "empty_segment_count": empty_count,
            "num_threads": NUM_THREADS,
            "note": "ASR on frozen VAD speech_regions; start/end copied; speaker=SPEECH.",
        }
        write_json(dest_path, payload)

    gigaam_version = getattr(gigaam, "__version__", "unknown")
    torch_version = getattr(torch, "__version__", "unknown")
    write_json(
        dest_dir / "_run.json",
        {
            "asr_id": job_id,
            "vad_id": spec["vad_id"],
            "status": "success",
            "failure_kind": "none",
            "execution_mode": "local",
            "provider": "gigaam",
            "asr_model": "v3_rnnt",
            "torch": True,
            "torch_version": torch_version,
            "gigaam_version": gigaam_version,
            "num_threads": NUM_THREADS,
            "asr_runtime_sec": round(time.monotonic() - started, 3),
            "asr_runtime_sec_per_clip": clip_runtimes,
            "peak_rss_mb": peak_rss_mb(),
            "empty_segment_count": empty_total,
            "source_dir": spec["source_dir"],
        },
    )
    del model
    gc.collect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--id", dest="job_id", default="", choices=["", *JOBS.keys()])
    args = parser.parse_args()
    require_clips_and_regions()
    if not args.job_id:
        for job_id in JOBS:
            subprocess.check_call([sys.executable, str(Path(__file__).resolve()), "--id", job_id])
        return
    run_job(args.job_id)


if __name__ == "__main__":
    main()

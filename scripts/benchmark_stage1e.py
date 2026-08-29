#!/usr/bin/env python3
"""Benchmark the four Stage 1e ASR models on one raw 25-second WAV."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from run_stage1e import extract

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/test_transformers.m4a"
WAV = ROOT / "results/asr/eval_clips/_extracts/speed_benchmark/test_transformers_0_25.wav"
OUTPUT = ROOT / "results/asr/eval_clips/speed_benchmark_25s.json"
MODELS = [
    ("gigaam_v3", "GigaAM v3 RNNT"),
    ("podlodka_turbo", "bond005/whisper-podlodka-turbo"),
    ("faster_whisper_large_v3", "faster-whisper large-v3"),
    ("podlodka_large_v3_ru", "bond005/whisper-large-v3-ru-podlodka"),
]


def timed_load(load: Callable[[], object]) -> tuple[object, float]:
    started = time.perf_counter()
    model = load()
    return model, time.perf_counter() - started


def benchmark_worker(model_id: str, wav: Path) -> dict[str, object]:
    if model_id == "gigaam_v3":
        import gigaam

        model, load_sec = timed_load(
            lambda: gigaam.load_model("v3_rnnt", fp16_encoder=False, device="cpu")
        )
        started = time.perf_counter()
        text = str(model.transcribe(str(wav)))
        inference_sec = time.perf_counter() - started
        model_name = "v3_rnnt"
        provider = "gigaam"
        settings = {"device": "cpu", "gain": "none"}
    elif model_id in {"podlodka_turbo", "podlodka_large_v3_ru"}:
        import torch
        from transformers import pipeline

        model_name = {
            "podlodka_turbo": "bond005/whisper-podlodka-turbo",
            "podlodka_large_v3_ru": "bond005/whisper-large-v3-ru-podlodka",
        }[model_id]
        model, load_sec = timed_load(
            lambda: pipeline(
                "automatic-speech-recognition",
                model=model_name,
                device=-1,
                dtype=torch.float32,
            )
        )
        started = time.perf_counter()
        result = model(
            str(wav),
            generate_kwargs={
                "language": "ru",
                "task": "transcribe",
                "condition_on_prev_tokens": False,
            },
            return_timestamps=False,
        )
        inference_sec = time.perf_counter() - started
        text = str(result["text"])
        provider = "transformers"
        settings = {
            "device": "cpu",
            "dtype": "float32",
            "language": "ru",
            "condition_on_prev_tokens": False,
            "gain": "none",
        }
    elif model_id == "faster_whisper_large_v3":
        from faster_whisper import WhisperModel

        model_name = "large-v3"
        model, load_sec = timed_load(
            lambda: WhisperModel(model_name, device="cpu", compute_type="int8")
        )
        started = time.perf_counter()
        segments, _ = model.transcribe(
            str(wav),
            language="ru",
            vad_filter=False,
            condition_on_previous_text=False,
        )
        text = " ".join(segment.text.strip() for segment in segments).strip()
        inference_sec = time.perf_counter() - started
        provider = "faster-whisper"
        settings = {
            "device": "cpu",
            "compute_type": "int8",
            "language": "ru",
            "vad_filter": False,
            "condition_on_previous_text": False,
            "gain": "none",
        }
    else:
        raise ValueError(f"Unknown model: {model_id}")

    return {
        "id": model_id,
        "model": model_name,
        "provider": provider,
        "execution_mode": "local",
        "load_sec": round(load_sec, 3),
        "inference_sec": round(inference_sec, 3),
        "real_time_factor": round(inference_sec / 25.0, 3),
        "output_chars": len(text.strip()),
        "settings": settings,
    }


def run_benchmark() -> None:
    import soundfile as sf

    extract(SOURCE, 0.0, 25.0, WAV, gain_db=0.0)
    info = sf.info(WAV)
    if info.frames != 25 * info.samplerate:
        raise RuntimeError(
            f"Benchmark WAV must be exactly 25 seconds: {info.frames}/{info.samplerate}"
        )

    payload: dict[str, object] = {
        "audio": str(WAV.relative_to(ROOT)),
        "source_audio": str(SOURCE.relative_to(ROOT)),
        "source_interval_sec": [0.0, 25.0],
        "duration_sec": 25.0,
        "sample_rate_hz": info.samplerate,
        "samples": info.frames,
        "processing": "none",
        "execution_mode": "local",
        "device": "cpu",
        "cache_state": "model files cached by the preceding Stage 1e run",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": [],
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    for model_id, _ in MODELS:
        started = time.perf_counter()
        process = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--worker", model_id, str(WAV)],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        )
        process_wall_sec = time.perf_counter() - started
        result_line = next(
            line for line in reversed(process.stdout.splitlines()) if line.startswith("__RESULT__")
        )
        result = json.loads(result_line.removeprefix("__RESULT__"))
        result["process_wall_sec"] = round(process_wall_sec, 3)
        result["total_model_sec"] = round(result["load_sec"] + result["inference_sec"], 3)
        payload["results"].append(result)
        OUTPUT.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", choices=[item[0] for item in MODELS])
    parser.add_argument("worker_args", nargs="*")
    args = parser.parse_args()
    if args.worker:
        if len(args.worker_args) != 1:
            parser.error("worker requires a WAV path")
        result = benchmark_worker(args.worker, Path(args.worker_args[0]))
        print("__RESULT__" + json.dumps(result, ensure_ascii=False))
    else:
        run_benchmark()


if __name__ == "__main__":
    main()

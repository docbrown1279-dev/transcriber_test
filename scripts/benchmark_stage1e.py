#!/usr/bin/env python3
"""Benchmark the four Stage 1e ASR models on one unprocessed 30-second clip."""

from __future__ import annotations

import gc
import json
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data/test_voice.m4a"
OUTPUT_DIR = ROOT / "results/asr/eval_clips/speed_benchmark"
WAV = OUTPUT_DIR / "test_voice_10s_40s.wav"
RESULT = OUTPUT_DIR / "benchmark.json"
SAMPLE_RATE = 16_000
DURATION_SEC = 30.0


def write_result(payload: dict[str, Any]) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def extract_benchmark_clip() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            "10.000000",
            "-to",
            "40.000000",
            "-i",
            str(SOURCE),
            "-map",
            "0:a:0",
            "-ac",
            "1",
            "-ar",
            str(SAMPLE_RATE),
            "-c:a",
            "pcm_s16le",
            str(WAV),
        ],
        check=True,
    )
    import soundfile as sf

    info = sf.info(WAV)
    expected = round(DURATION_SEC * SAMPLE_RATE)
    if info.frames != expected:
        raise RuntimeError(
            f"Benchmark WAV must contain exactly {expected} samples, got {info.frames}"
        )


def release_model() -> None:
    gc.collect()
    try:
        import ctypes

        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except (OSError, AttributeError):
        pass


def benchmark(
    payload: dict[str, Any],
    model_id: str,
    provider: str,
    loader: Callable[[], Any],
    infer: Callable[[Any], str],
    notes: str,
) -> None:
    load_started = time.perf_counter()
    model = loader()
    load_sec = time.perf_counter() - load_started

    inference_started = time.perf_counter()
    text = infer(model)
    inference_sec = time.perf_counter() - inference_started
    if not text.strip():
        raise RuntimeError(f"{model_id} returned empty text")

    payload["results"].append(
        {
            "model": model_id,
            "provider": provider,
            "execution_mode": "local",
            "device": "cpu",
            "status": "success",
            "load_sec": round(load_sec, 3),
            "inference_sec": round(inference_sec, 3),
            "total_sec": round(load_sec + inference_sec, 3),
            "real_time_factor": round(inference_sec / DURATION_SEC, 4),
            "recognized_chars": len(text.strip()),
            "notes": notes,
        }
    )
    write_result(payload)
    del model
    release_model()


def main() -> None:
    extract_benchmark_clip()
    payload: dict[str, Any] = {
        "audio": str(WAV.relative_to(ROOT)),
        "source_audio": str(SOURCE.relative_to(ROOT)),
        "source_interval_sec": {"start": 10.0, "end": 40.0},
        "duration_sec": DURATION_SEC,
        "sample_rate_hz": SAMPLE_RATE,
        "channels": 1,
        "sample_count": round(DURATION_SEC * SAMPLE_RATE),
        "processing": "none (PCM decode/resample only; no filters)",
        "language": "ru",
        "device": "cpu",
        "measurement": "single run; model load and inference measured separately; local caches warm",
        "results": [],
    }
    write_result(payload)

    import gigaam

    def load_gigaam() -> Any:
        return gigaam.load_model("v3_rnnt", fp16_encoder=False, device="cpu")

    def infer_gigaam(model: Any) -> str:
        # Public transcribe() rejects >25 s before inference. This is the same
        # encoder/RNNT path without that API guard and without long-form VAD.
        wav, length = model.prepare_wav(str(WAV))
        encoded, encoded_len = model.forward(wav, length)
        text, _ = model._decode(encoded, encoded_len, length, False)[0]
        return text

    benchmark(
        payload,
        "gigaam-v3-rnnt",
        "gigaam",
        load_gigaam,
        infer_gigaam,
        "Один файл 30 с; прямой encoder+RNNT decode без 25-секундного API guard и без VAD.",
    )

    import soundfile as sf
    import torch
    from transformers import pipeline

    samples, sample_rate = sf.read(WAV, dtype="float32")

    def transformer_loader(model_id: str) -> Callable[[], Any]:
        return lambda: pipeline(
            "automatic-speech-recognition",
            model=model_id,
            device=-1,
            dtype=torch.float32,
        )

    def infer_transformer(model: Any) -> str:
        result = model(
            {"array": samples, "sampling_rate": sample_rate},
            generate_kwargs={
                "language": "ru",
                "task": "transcribe",
                "condition_on_prev_tokens": False,
            },
            return_timestamps=False,
        )
        return result["text"]

    benchmark(
        payload,
        "bond005/whisper-podlodka-turbo",
        "transformers",
        transformer_loader("bond005/whisper-podlodka-turbo"),
        infer_transformer,
        "language=ru; condition_on_prev_tokens=false; без VAD.",
    )

    from faster_whisper import WhisperModel

    def load_faster_whisper() -> Any:
        return WhisperModel("large-v3", device="cpu", compute_type="int8")

    def infer_faster_whisper(model: Any) -> str:
        segments, _ = model.transcribe(
            str(WAV),
            language="ru",
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments)

    benchmark(
        payload,
        "faster-whisper-large-v3",
        "faster-whisper",
        load_faster_whisper,
        infer_faster_whisper,
        "CPU int8; language=ru; vad_filter=false; condition_on_previous_text=false.",
    )

    benchmark(
        payload,
        "bond005/whisper-large-v3-ru-podlodka",
        "transformers",
        transformer_loader("bond005/whisper-large-v3-ru-podlodka"),
        infer_transformer,
        "language=ru; condition_on_prev_tokens=false; без VAD.",
    )


if __name__ == "__main__":
    main()

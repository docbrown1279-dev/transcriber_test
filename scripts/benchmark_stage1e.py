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

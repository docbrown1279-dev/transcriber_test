#!/usr/bin/env python3
"""Run one bounded faster-whisper experiment and write reusable artifacts."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pymorphy3
from faster_whisper import WhisperModel


WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё-]+")
CYRILLIC_RE = re.compile(r"[А-Яа-яЁё]")
URL_QUERY_RE = re.compile(r"(https?://[^\s?]+)\?[^\s]+")


def sanitize_error(error: BaseException) -> str:
    message = f"{type(error).__name__}: {error}"
    return URL_QUERY_RE.sub(r"\1?[redacted]", message)[:2000]


def russian_word_metrics(text: str) -> tuple[float | None, list[str]]:
    morphology = pymorphy3.MorphAnalyzer()
    words = [word.strip("-").lower() for word in WORD_RE.findall(text)]
    words = [word for word in words if word]
    if not words:
        return None, []

    known = 0
    oov: set[str] = set()
    for word in words:
        is_russian = bool(CYRILLIC_RE.search(word))
        is_known = is_russian and any(parse.is_known for parse in morphology.parse(word))
        if is_known:
            known += 1
        else:
            oov.add(word)
    return known / len(words), sorted(oov)


def sample_fragments(segments: list[dict[str, object]], count: int = 3) -> list[dict[str, object]]:
    if not segments:
        return []
    indices = sorted(
        {
            round(index * (len(segments) - 1) / max(count - 1, 1))
            for index in range(min(count, len(segments)))
        }
    )
    return [segments[index] for index in indices]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--attempt", required=True, type=int, choices=range(1, 4))
    parser.add_argument("--input", default="data/fixtures/meeting_sample.m4a")
    parser.add_argument("--output-dir", default="results/asr")
    parser.add_argument("--cpu-threads", type=int, default=4)
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"attempt-{args.attempt}-{args.model.replace('/', '-')}"
    json_path = output_dir / f"{stem}.json"
    text_path = output_dir / f"{stem}.txt"
    started = time.monotonic()
    artifact: dict[str, object] = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "library": "faster-whisper",
        "model": args.model,
        "attempt": args.attempt,
        "input": args.input,
        "device": "cpu",
        "compute_type": "int8",
        "status": "fail",
    }

    try:
        model = WhisperModel(
            args.model,
            device="cpu",
            compute_type="int8",
            cpu_threads=args.cpu_threads,
            download_root=".cache/huggingface",
        )
        generated_segments, info = model.transcribe(
            args.input,
            language="ru",
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=True,
        )
        segments = [
            {
                "start": round(segment.start, 3),
                "end": round(segment.end, 3),
                "text": segment.text.strip(),
            }
            for segment in generated_segments
        ]
        text = "\n".join(segment["text"] for segment in segments)
        ratio, oov = russian_word_metrics(text)
        text_path.write_text(text + "\n", encoding="utf-8")
        artifact.update(
            {
                "status": "success",
                "detected_language": info.language,
                "language_probability": info.language_probability,
                "duration_sec": info.duration,
                "duration_after_vad_sec": info.duration_after_vad,
                "rw_ratio": ratio,
                "oov_words": oov,
                "segments": segments,
                "sample_fragments": sample_fragments(segments),
                "text_artifact": str(text_path),
            }
        )
    except Exception as error:
        artifact["error"] = sanitize_error(error)

    artifact["runtime_sec"] = round(time.monotonic() - started, 3)
    json_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({key: artifact.get(key) for key in ("status", "model", "attempt", "runtime_sec", "error")}, ensure_ascii=False))
    return 0 if artifact["status"] == "success" else 1


if __name__ == "__main__":
    sys.exit(main())

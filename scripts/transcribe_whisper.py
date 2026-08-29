#!/usr/bin/env python3
"""Run one bounded local faster-whisper transcription attempt."""

import argparse
import json
import platform
import time
from pathlib import Path

from faster_whisper import WhisperModel


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="medium")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    model = WhisperModel(
        args.model,
        device="cpu",
        compute_type="int8",
        cpu_threads=args.threads,
        num_workers=1,
    )
    segments_iter, info = model.transcribe(
        str(args.input),
        language="ru",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=True,
    )
    segments = [
        {
            "id": segment.id,
            "start": round(segment.start, 3),
            "end": round(segment.end, 3),
            "text": segment.text.strip(),
        }
        for segment in segments_iter
    ]
    runtime_sec = round(time.monotonic() - started, 3)
    payload = {
        "execution_mode": "local",
        "provider": "faster-whisper",
        "model": args.model,
        "compute_type": "int8",
        "cpu_threads": args.threads,
        "host": platform.platform(),
        "input_artifact": str(args.input),
        "language": info.language,
        "language_probability": round(info.language_probability, 6),
        "audio_duration_sec": round(info.duration, 3),
        "runtime_sec": runtime_sec,
        "segments": segments,
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    args.output.with_suffix(".txt").write_text(
        "\n".join(segment["text"] for segment in segments) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "segments": len(segments),
                "runtime_sec": runtime_sec,
                "language": info.language,
            }
        )
    )


if __name__ == "__main__":
    main()

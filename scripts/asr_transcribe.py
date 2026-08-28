#!/usr/bin/env python3
"""Run faster-whisper ASR and write transcript + segments JSON."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--model", default="medium")
    parser.add_argument("--out", required=True, help="Output JSON path")
    parser.add_argument("--language", default="ru")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--beam-size", type=int, default=5)
    parser.add_argument("--vad", action="store_true", default=True)
    parser.add_argument("--no-vad", action="store_false", dest="vad")
    args = parser.parse_args()

    from faster_whisper import WhisperModel

    audio = Path(args.audio)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    model = WhisperModel(
        args.model,
        device=args.device,
        compute_type=args.compute_type,
    )
    load_sec = time.time() - t0

    t1 = time.time()
    segments_iter, info = model.transcribe(
        str(audio),
        language=args.language,
        beam_size=args.beam_size,
        vad_filter=args.vad,
        word_timestamps=False,
    )
    segments = []
    texts = []
    for seg in segments_iter:
        item = {
            "id": seg.id,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": seg.text.strip(),
        }
        segments.append(item)
        if item["text"]:
            texts.append(item["text"])
    infer_sec = time.time() - t1
    total_sec = time.time() - t0

    payload = {
        "lib": "faster-whisper",
        "model": args.model,
        "device": args.device,
        "compute_type": args.compute_type,
        "beam_size": args.beam_size,
        "vad_filter": args.vad,
        "audio": str(audio),
        "language": info.language,
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "load_sec": round(load_sec, 2),
        "infer_sec": round(infer_sec, 2),
        "runtime_sec": round(total_sec, 2),
        "text": " ".join(texts),
        "segments": segments,
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    txt_path = out.with_suffix(".txt")
    txt_path.write_text(payload["text"] + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out),
                "segments": len(segments),
                "chars": len(payload["text"]),
                "runtime_sec": payload["runtime_sec"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

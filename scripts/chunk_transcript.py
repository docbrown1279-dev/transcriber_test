#!/usr/bin/env python3
"""Create semantic transcript chunks from local sentence embeddings."""

import argparse
import json
import time
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("segments", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    parser.add_argument("--threshold", type=float, default=0.7)
    args = parser.parse_args()

    source = json.loads(args.segments.read_text(encoding="utf-8"))
    segments = [segment for segment in source["segments"] if segment["text"].strip()]
    texts = [f"passage: {segment['text']}" for segment in segments]

    started = time.monotonic()
    model = SentenceTransformer(args.model, device="cpu")
    vectors = model.encode(
        texts,
        batch_size=16,
        normalize_embeddings=True,
        show_progress_bar=True,
    )
    similarities = np.sum(vectors[:-1] * vectors[1:], axis=1).tolist()

    chunks = []
    current = []
    for index, segment in enumerate(segments):
        current.append(segment)
        is_break = index == len(segments) - 1 or similarities[index] < args.threshold
        if is_break:
            chunks.append(
                {
                    "id": len(chunks),
                    "start": current[0]["start"],
                    "end": current[-1]["end"],
                    "text": " ".join(item["text"] for item in current),
                    "break_similarity": (
                        round(similarities[index], 6)
                        if index < len(similarities)
                        else None
                    ),
                }
            )
            current = []

    payload = {
        "execution_mode": "local",
        "provider": "sentence-transformers",
        "embedding_model": args.model,
        "input_artifact": str(args.segments),
        "threshold": args.threshold,
        "runtime_sec": round(time.monotonic() - started, 3),
        "segment_count": len(segments),
        "num_chunks": len(chunks),
        "similarity_summary": {
            "min": round(min(similarities), 6) if similarities else None,
            "median": round(float(np.median(similarities)), 6)
            if similarities
            else None,
            "max": round(max(similarities), 6) if similarities else None,
        },
        "chunks": chunks,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "segments": len(segments),
                "chunks": len(chunks),
                "runtime_sec": payload["runtime_sec"],
            }
        )
    )


if __name__ == "__main__":
    main()

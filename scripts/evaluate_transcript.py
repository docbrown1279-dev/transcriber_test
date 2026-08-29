#!/usr/bin/env python3
"""Calculate the Stage 1 Russian-word metric and deterministic samples."""

import argparse
import collections
import json
import re
from pathlib import Path

import pymorphy3

WORD_RE = re.compile(r"[А-Яа-яЁё]+")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("segments", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--samples", type=int, default=4)
    args = parser.parse_args()

    text = args.transcript.read_text(encoding="utf-8")
    words = [word.lower().replace("ё", "е") for word in WORD_RE.findall(text)]
    morph = pymorphy3.MorphAnalyzer()
    known = [morph.word_is_known(word) for word in words]
    oov_counts = collections.Counter(
        word for word, is_known in zip(words, known) if not is_known
    )

    segment_data = json.loads(args.segments.read_text(encoding="utf-8"))["segments"]
    candidates = [
        {
            "start": segment_data[index]["start"],
            "end": segment_data[min(index + 1, len(segment_data) - 1)]["end"],
            "text": " ".join(
                item["text"]
                for item in segment_data[index : min(index + 2, len(segment_data))]
            ),
        }
        for index in range(max(0, len(segment_data) - 1))
    ]
    if candidates:
        indices = sorted(
            {
                round(position * (len(candidates) - 1) / max(args.samples - 1, 1))
                for position in range(args.samples)
            }
        )
        samples = [candidates[index] for index in indices]
    else:
        samples = []

    payload = {
        "metric": "pymorphy3.word_is_known over Cyrillic tokens",
        "total_russian_script_words": len(words),
        "known_russian_words": sum(known),
        "rw_ratio": round(sum(known) / len(words), 6) if words else 0.0,
        "quality_gate": 0.9,
        "oov_words": [
            {"word": word, "count": count}
            for word, count in oov_counts.most_common()
        ],
        "sample_fragments": samples,
        "sample_check": "pending_manual_review",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "rw_ratio": payload["rw_ratio"],
                "words": len(words),
                "oov_unique": len(oov_counts),
            }
        )
    )


if __name__ == "__main__":
    main()

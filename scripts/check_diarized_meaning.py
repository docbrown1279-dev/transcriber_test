#!/usr/bin/env python3
"""Sample diarized fragments and assess their coherence with local Qwen3."""

from __future__ import annotations

import argparse
import json
import random
import re
import time
from collections import defaultdict
from pathlib import Path

from llama_cpp import Llama


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sample_fragments(transcript: dict, seed: int, per_speaker: int) -> list[dict]:
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    for segment in transcript["segments"]:
        speaker = segment.get("speaker")
        text = clean_text(segment.get("text", ""))
        if speaker and len(text) >= 25:
            by_speaker[speaker].append(
                {
                    "speaker": speaker,
                    "start": round(segment["start"], 3),
                    "end": round(segment["end"], 3),
                    "text": text,
                }
            )

    rng = random.Random(seed)
    samples: list[dict] = []
    for speaker in sorted(by_speaker):
        candidates = by_speaker[speaker]
        selected = rng.sample(candidates, min(per_speaker, len(candidates)))
        selected.sort(key=lambda item: item["start"])
        for index, fragment in enumerate(selected, start=1):
            samples.append({"id": f"{speaker}_{index}", **fragment})
    return samples


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20260829)
    parser.add_argument("--per-speaker", type=int, default=3)
    args = parser.parse_args()

    transcript = json.loads(args.transcript.read_text(encoding="utf-8"))
    samples = sample_fragments(transcript, args.seed, args.per_speaker)
    formatted = "\n".join(
        (
            f"{item['id']} | {item['start']:.3f}-{item['end']:.3f} | "
            f"{item['text']}"
        )
        for item in samples
    )
    prompt = f"""Оцени качество распознавания каждого фрагмента.

Главный вопрос: это связная русская речь совещания или набор правдоподобных,
но бессмысленных/испорченных фраз? Иностранные слова, случайные вставки,
обрывки и невозможные сочетания считай признаком incoherent. Не исправляй и
не пересказывай текст.

Верни JSON без markdown:
{{
  "assessments": [
    {{"id": "...", "verdict": "coherent|incoherent", "reason": "кратко"}}
  ],
  "coherent_count": 0,
  "incoherent_count": 0,
  "overall": "coherent|incoherent",
  "rationale": "краткое обоснование"
}}

Фрагменты:
{formatted}

/no_think"""

    started = time.monotonic()
    llm = Llama(
        model_path=str(args.model),
        n_ctx=8192,
        n_threads=args.threads,
        n_threads_batch=args.threads,
        n_batch=512,
        verbose=False,
    )
    response = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты строгий контролёр качества русской стенограммы. "
                    "Следуй формату и не додумывай отсутствующий смысл."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        max_tokens=2048,
        temperature=0.1,
        top_p=0.9,
    )
    runtime_sec = round(time.monotonic() - started, 3)
    raw_response = response["choices"][0]["message"]["content"].strip()
    parsed_response = None
    try:
        parsed_response = json.loads(raw_response)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw_response, re.DOTALL)
        if match:
            try:
                parsed_response = json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

    output = {
        "execution_mode": "local",
        "provider": "llama.cpp",
        "model": args.model.name,
        "input_artifact": str(args.transcript),
        "seed": args.seed,
        "fragments_per_speaker": args.per_speaker,
        "samples": samples,
        "runtime_sec": runtime_sec,
        "usage": response.get("usage"),
        "assessment": parsed_response,
        "raw_response": raw_response,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "runtime_sec": runtime_sec,
                "sample_count": len(samples),
                "parsed": parsed_response is not None,
                "overall": (
                    parsed_response.get("overall") if parsed_response else None
                ),
            }
        )
    )


if __name__ == "__main__":
    main()

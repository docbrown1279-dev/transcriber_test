#!/usr/bin/env python3
"""One correction: split oversized Qwen title groups toward 5–30 chapters."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from llama_cpp import Llama

from merge_titles_stage2 import (
    MERGED_CHUNKS,
    OUT,
    SYSTEM,
    clip_title,
    extract_json_array,
    validate_groups,
    write_json,
)

ROOT = Path(__file__).resolve().parents[1]
REFINE_USER = (
    "/no_think\n"
    "Предыдущий ответ склеил список в {n} глав — это мало (нужно 5–30, лучше 12–15). "
    "Разбей только слишком широкие группы на соседние подгруппы. "
    "Небольшие группы (2–4 пункта) оставь. Не переставляй и не склеивай несоседей. "
    "Заголовок группы — не больше 10 русских слов. "
    "Верни только JSON-массив [{{'ids':[0,1],'title':'...'}}].\n\n"
    "Исходные заголовки:\n{items}\n\nПредыдущая склейка:\n{previous}"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--titles", type=Path, default=ROOT / "results/llm/2/titles.json")
    parser.add_argument("--previous", type=Path, default=OUT)
    parser.add_argument("--chunks", type=Path, default=ROOT / "results/chunking/2/attempt_2_chunks.json")
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    titles = json.loads(args.titles.read_text(encoding="utf-8"))
    previous = json.loads(args.previous.read_text(encoding="utf-8"))
    chunks_src = json.loads(args.chunks.read_text(encoding="utf-8"))
    per_chunk = titles["per_chunk"]
    items = "\n".join(
        f"{row['id']}. [{row['start']:.1f}–{row['end']:.1f}] {row['title']}"
        for row in per_chunk
    )
    prev_text = json.dumps(previous["groups"], ensure_ascii=False)
    llm = Llama(
        model_path=str(args.model),
        n_ctx=4096,
        n_threads=args.threads,
        n_threads_batch=args.threads,
        n_batch=256,
        verbose=False,
    )
    started = time.monotonic()
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": REFINE_USER.format(
                    n=previous["num_merged"], items=items, previous=prev_text
                ),
            },
        ],
        max_tokens=2048,
        temperature=0.2,
        top_p=0.9,
    )
    raw = response["choices"][0]["message"]["content"] or ""
    runtime_sec = round(time.monotonic() - started, 3)
    groups = validate_groups(extract_json_array(raw), len(per_chunk))
    chunk_by_id = {int(item["id"]): item for item in chunks_src["chunks"]}
    title_by_id = {int(row["id"]): row["title"] for row in per_chunk}
    merged = []
    for group_id, group in enumerate(groups):
        ids = group["ids"]
        members = [chunk_by_id[index] for index in ids]
        speakers: list[str] = []
        for member in members:
            for speaker in member["speakers"]:
                if speaker not in speakers:
                    speakers.append(speaker)
        title = group["title"] or title_by_id[ids[0]]
        merged.append(
            {
                "id": group_id,
                "start": members[0]["start"],
                "end": members[-1]["end"],
                "text": " ".join(member["text"] for member in members).strip(),
                "speakers": speakers,
                "n_words": sum(int(member["n_words"]) for member in members),
                "title": clip_title(title),
                "source_chunk_ids": ids,
                "source_titles": [title_by_id[index] for index in ids],
            }
        )
    payload = {
        "execution_mode": "local",
        "provider": "llama.cpp",
        "model": args.model.name,
        "input_artifact": str(args.previous.relative_to(ROOT)),
        "phase": "refine_after_4_groups",
        "llm_runtime_sec": runtime_sec,
        "raw": raw,
        "num_source_chunks": len(per_chunk),
        "num_merged_before": previous["num_merged"],
        "num_merged": len(merged),
        "in_target_range": 5 <= len(merged) <= 30,
        "groups": [{"ids": group["ids"], "title": group["title"]} for group in groups],
        "chunks": merged,
    }
    write_json(ROOT / "results/llm/2/title_merge_refined.json", payload)
    write_json(
        MERGED_CHUNKS,
        {
            "execution_mode": "local",
            "provider": "llama.cpp",
            "embedding_model": chunks_src.get("embedding_model"),
            "input_artifact": "results/llm/2/titles.json",
            "source_attempt": 2,
            "method": "qwen_title_adjacent_merge_refined",
            "num_chunks": len(merged),
            "in_target_range": payload["in_target_range"],
            "llm_runtime_sec": runtime_sec,
            "chunks": [
                {
                    "id": item["id"],
                    "start": item["start"],
                    "end": item["end"],
                    "text": item["text"],
                    "speakers": item["speakers"],
                    "n_words": item["n_words"],
                    "title": item["title"],
                }
                for item in merged
            ],
        },
    )
    print(
        json.dumps(
            {
                "num_merged": len(merged),
                "in_target_range": payload["in_target_range"],
                "llm_runtime_sec": runtime_sec,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

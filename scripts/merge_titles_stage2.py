#!/usr/bin/env python3
"""Merge attempt-2 titles with local Qwen into 5–30 adjacent chapters."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from llama_cpp import Llama

ROOT = Path(__file__).resolve().parents[1]
TITLES = ROOT / "results" / "llm" / "2" / "titles.json"
CHUNKS = ROOT / "results" / "chunking" / "2" / "attempt_2_chunks.json"
OUT = ROOT / "results" / "llm" / "2" / "title_merge.json"
MERGED_CHUNKS = ROOT / "results" / "chunking" / "2" / "chunks_from_titles.json"
WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)

SYSTEM = (
    "Ты склеиваешь соседние заголовки глав совещания. "
    "Можно объединять только идущие подряд пункты. "
    "Нельзя переставлять и нельзя склеивать несоседей. "
    "Не выдумывай людей, роли, решения, числа и факты. "
    "Не пиши саммари встречи."
)
USER = (
    "/no_think\n"
    "Ниже список заголовков по времени. Склей соседние пункты с одной темой "
    "так, чтобы получилось от 5 до 30 глав, лучше около 12–15. "
    "Для каждой группы дай новый заголовок не больше 10 русских слов. "
    "Верни только JSON-массив вида "
    '[{{"ids":[0,1],"title":"..."}}] без текста вокруг.\n\n{items}'
)
RETRY = (
    "/no_think\n"
    "Ответ должен быть только JSON-массивом "
    '[{{"ids":[0,1],"title":"..."}}]. Без markdown и без пояснений.\n\n{items}'
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clip_title(text: str) -> str:
    cleaned = THINK_RE.sub("", text).strip().strip("\"'«»").strip()
    cleaned = cleaned.splitlines()[0].strip() if cleaned else text.strip()
    tokens = WORD_RE.findall(cleaned)
    if len(tokens) <= 10:
        return cleaned
    parts = []
    cursor = 0
    for token in tokens[:10]:
        match = re.search(re.escape(token), cleaned[cursor:], re.I)
        if not match:
            parts.append(token)
            continue
        parts.append(cleaned[cursor + match.start() : cursor + match.end()])
        cursor = cursor + match.end()
    return " ".join(parts)


def strip_think(text: str) -> str:
    return THINK_RE.sub("", text).strip()


def extract_json_array(text: str) -> list[dict[str, Any]]:
    cleaned = strip_think(text)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned.strip(), flags=re.I)
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON array in model output")
    payload = json.loads(cleaned[start : end + 1])
    if not isinstance(payload, list) or not payload:
        raise ValueError("JSON array is empty")
    rows = []
    for item in payload:
        ids = [int(value) for value in item["ids"]]
        if not ids:
            raise ValueError("group without ids")
        rows.append({"ids": ids, "title": clip_title(str(item["title"]))})
    return rows


def validate_groups(groups: list[dict[str, Any]], n_chunks: int) -> list[dict[str, Any]]:
    seen: set[int] = set()
    normalized = []
    for group in groups:
        ids = group["ids"]
        if ids != list(range(ids[0], ids[-1] + 1)):
            raise ValueError(f"non-adjacent ids: {ids}")
        if any(index in seen for index in ids):
            raise ValueError(f"overlapping ids: {ids}")
        if min(ids) < 0 or max(ids) >= n_chunks:
            raise ValueError(f"id out of range: {ids}")
        seen.update(ids)
        normalized.append(group)
    missing = [index for index in range(n_chunks) if index not in seen]
    if missing:
        # Keep leftovers as singleton chapters so we do not drop time.
        for index in missing:
            insert_at = next(
                (pos for pos, group in enumerate(normalized) if group["ids"][0] > index),
                len(normalized),
            )
            normalized.insert(insert_at, {"ids": [index], "title": ""})
    return normalized


def ask(llm: Llama, items: str, retry: bool) -> tuple[str, float]:
    started = time.monotonic()
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": (RETRY if retry else USER).format(items=items)},
        ],
        max_tokens=2048,
        temperature=0.2,
        top_p=0.9,
    )
    text = response["choices"][0]["message"]["content"] or ""
    return text, round(time.monotonic() - started, 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--titles", type=Path, default=TITLES)
    parser.add_argument("--chunks", type=Path, default=CHUNKS)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    titles = json.loads(args.titles.read_text(encoding="utf-8"))
    chunks_src = json.loads(args.chunks.read_text(encoding="utf-8"))
    per_chunk = titles["per_chunk"]
    chunk_by_id = {int(item["id"]): item for item in chunks_src["chunks"]}
    items = "\n".join(
        f"{row['id']}. [{row['start']:.1f}–{row['end']:.1f}] {row['title']}"
        for row in per_chunk
    )
    llm = Llama(
        model_path=str(args.model),
        n_ctx=4096,
        n_threads=args.threads,
        n_threads_batch=args.threads,
        n_batch=256,
        verbose=False,
    )
    raw, first_sec = ask(llm, items, retry=False)
    parse_error = None
    groups = None
    try:
        groups = validate_groups(extract_json_array(raw), len(per_chunk))
        used_retry = False
        second_sec = 0.0
        second_raw = ""
    except Exception as exc:
        parse_error = f"{type(exc).__name__}: {exc}"
        second_raw, second_sec = ask(llm, items, retry=True)
        groups = validate_groups(extract_json_array(second_raw), len(per_chunk))
        used_retry = True

    # Fill singleton titles from the original chunk title if the model skipped them.
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
        text = " ".join(member["text"] for member in members).strip()
        merged.append(
            {
                "id": group_id,
                "start": members[0]["start"],
                "end": members[-1]["end"],
                "text": text,
                "speakers": speakers,
                "n_words": sum(int(member["n_words"]) for member in members),
                "title": title,
                "source_chunk_ids": ids,
                "source_titles": [title_by_id[index] for index in ids],
            }
        )
    runtime_sec = round(first_sec + second_sec, 3)
    payload = {
        "execution_mode": "local",
        "provider": "llama.cpp",
        "model": args.model.name,
        "input_artifact": str(args.titles.relative_to(ROOT))
        if args.titles.is_relative_to(ROOT)
        else str(args.titles),
        "llm_runtime_sec": runtime_sec,
        "llm_runtime_first_sec": first_sec,
        "llm_runtime_retry_sec": second_sec,
        "used_retry": used_retry,
        "parse_error_first": parse_error,
        "raw_first": raw,
        "raw_retry": second_raw,
        "num_source_chunks": len(per_chunk),
        "num_merged": len(merged),
        "in_target_range": 5 <= len(merged) <= 30,
        "groups": [{"ids": group["ids"], "title": group["title"]} for group in groups],
        "chunks": merged,
    }
    write_json(OUT, payload)
    write_json(
        MERGED_CHUNKS,
        {
            "execution_mode": "local",
            "provider": "llama.cpp",
            "embedding_model": chunks_src.get("embedding_model"),
            "input_artifact": str(args.titles.relative_to(ROOT))
            if args.titles.is_relative_to(ROOT)
            else str(args.titles),
            "source_attempt": 2,
            "method": "qwen_title_adjacent_merge",
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
                "used_retry": used_retry,
                "llm_runtime_sec": runtime_sec,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

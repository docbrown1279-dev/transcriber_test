#!/usr/bin/env python3
"""Local Qwen3-8B titles for Stage 2 chunks. Text only, <=10 Russian words."""

from __future__ import annotations

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from llama_cpp import Llama

ROOT = Path(__file__).resolve().parents[1]
CHUNKS = ROOT / "results" / "chunking" / "2" / "chunks.json"
OUT = ROOT / "results" / "llm" / "2" / "titles.json"
WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)

SYSTEM = (
    "Ты даёшь короткие заголовки глав совещания только по данному тексту. "
    "Не выдумывай ответственных, роли, решения, числа и факты, которых нет в тексте. "
    "Не пиши саммари встречи."
)
USER = (
    "/no_think\n"
    "Дай заголовок не больше 10 русских слов для этого фрагмента. "
    "Только заголовок, без кавычек и без точки в конце.\n\nТЕКСТ:\n{text}"
)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def clip_title(text: str) -> str:
    cleaned = THINK_RE.sub("", text).strip().strip("\"'«»").strip()
    cleaned = cleaned.splitlines()[0].strip()
    tokens = WORD_RE.findall(cleaned)
    if len(tokens) <= 10:
        return cleaned
    kept = tokens[:10]
    # Rebuild from original words in order.
    pattern = re.compile("|".join(re.escape(token) for token in kept), re.I)
    parts = []
    cursor = 0
    for token in kept:
        match = re.search(re.escape(token), cleaned[cursor:], re.I)
        if not match:
            parts.append(token)
            continue
        parts.append(cleaned[cursor + match.start() : cursor + match.end()])
        cursor = cursor + match.end()
    return " ".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chunks", type=Path, default=CHUNKS)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    source = json.loads(args.chunks.read_text(encoding="utf-8"))
    chunks = source["chunks"]
    done: dict[int, dict[str, Any]] = {}
    if args.out.exists():
        previous = json.loads(args.out.read_text(encoding="utf-8"))
        for row in previous.get("per_chunk", []):
            if row.get("title"):
                done[int(row["id"])] = row
    started = time.monotonic()
    llm = Llama(
        model_path=str(args.model),
        n_ctx=4096,
        n_threads=args.threads,
        n_threads_batch=args.threads,
        n_batch=256,
        verbose=False,
    )
    rows = []
    for chunk in chunks:
        existing = done.get(int(chunk["id"]))
        if existing:
            rows.append(existing)
            chunk["title"] = existing["title"]
            continue
        item_started = time.monotonic()
        response = llm.create_chat_completion(
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": USER.format(text=chunk["text"])},
            ],
            max_tokens=48,
            temperature=0.2,
            top_p=0.9,
        )
        raw = (response["choices"][0]["message"]["content"] or "").strip()
        title = clip_title(raw)
        item_runtime = round(time.monotonic() - item_started, 3)
        row = {
            "id": chunk["id"],
            "start": chunk["start"],
            "end": chunk["end"],
            "title": title,
            "raw_title": raw,
            "title_words": len(WORD_RE.findall(title)),
            "llm_runtime_sec": item_runtime,
        }
        rows.append(row)
        chunk["title"] = title
        payload = {
            "execution_mode": "local",
            "provider": "llama.cpp",
            "model": args.model.name,
            "input_artifact": str(args.chunks.relative_to(ROOT))
            if args.chunks.is_relative_to(ROOT)
            else str(args.chunks),
            "llm_runtime_sec": round(time.monotonic() - started, 3),
            "per_chunk": rows,
        }
        write_json(args.out, payload)
        print(json.dumps({"done": chunk["id"], "title": title, "sec": item_runtime}, ensure_ascii=False), flush=True)
    runtime_sec = round(time.monotonic() - started, 3)
    payload = {
        "execution_mode": "local",
        "provider": "llama.cpp",
        "model": args.model.name,
        "input_artifact": str(args.chunks.relative_to(ROOT))
        if args.chunks.is_relative_to(ROOT)
        else str(args.chunks),
        "llm_runtime_sec": runtime_sec,
        "per_chunk": rows,
    }
    write_json(args.out, payload)
    titled_path = args.chunks.with_name(args.chunks.stem + "_titled.json")
    titled_path.write_text(
        json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "chunks": len(rows),
                "llm_runtime_sec": runtime_sec,
                "per_chunk": [row["llm_runtime_sec"] for row in rows],
            }
        )
    )


if __name__ == "__main__":
    main()

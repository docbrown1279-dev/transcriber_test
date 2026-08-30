#!/usr/bin/env python3
"""Generate Qwen titles after source-boundary validation. Never edits timestamps."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import argparse
import json
import time
from pathlib import Path
from typing import Any

from llama_cpp import Llama

from stage2b_common import (
    LLM_DIR,
    OUT_DIR,
    clip_title,
    first_last_words,
    review_sheet,
    write_json,
)

SYSTEM = (
    "Ты даёшь короткие заголовки глав совещания только по данным названиям и краю текста. "
    "Не выдумывай ответственных, роли, решения, числа и факты. "
    "Не пиши саммари встречи. Не указывай время."
)
USER_A = (
    "/no_think\n"
    "Дай заголовок не больше 10 русских слов для этой группы. "
    "Опирайся на старые названия и первые/последние слова. "
    "Только заголовок, без кавычек и без точки в конце.\n\n"
    "СТАРые НАЗВАНИЯ:\n{titles}\n\nНАЧАЛО:\n{first}\n\nКОНЕЦ:\n{last}"
)
USER_PLAIN = (
    "/no_think\n"
    "Дай заголовок не больше 10 русских слов для этого фрагмента. "
    "Только заголовок, без кавычек и без точки в конце.\n\nТЕКСТ:\n{text}"
)


def title_one(llm: Llama, prompt: str) -> tuple[str, str, float]:
    started = time.monotonic()
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": prompt},
        ],
        max_tokens=48,
        temperature=0.2,
        top_p=0.9,
    )
    raw = (response["choices"][0]["message"]["content"] or "").strip()
    return clip_title(raw), raw, round(time.monotonic() - started, 3)


def apply_titles(
    chapters_path: Path,
    llm: Llama,
    *,
    mode: str,
    out_name: str,
    review_name: str,
    method: str,
) -> dict[str, Any]:
    payload = json.loads(chapters_path.read_text(encoding="utf-8"))
    chapters = payload["chapters"]
    rows = []
    for chapter in chapters:
        locked = {
            "start": chapter["start"],
            "end": chapter["end"],
            "source_ids": list(chapter.get("source_ids") or chapter["leaf_ids"]),
            "start_source_id": chapter.get("start_source_id"),
            "end_source_id": chapter.get("end_source_id"),
        }
        source_ids = list(chapter.get("source_ids") or chapter["leaf_ids"])
        existing = (chapter.get("title") or "").strip()
        if mode == "a" and len(source_ids) == 1 and existing and " | " not in existing:
            rows.append(
                {
                    "id": chapter["id"],
                    "title": existing,
                    "raw_title": existing,
                    "llm_runtime_sec": 0.0,
                    "start": locked["start"],
                    "end": locked["end"],
                    "source_ids": locked["source_ids"],
                    "reused_existing": True,
                }
            )
            continue
        if mode == "a":
            member_titles = existing
            first, last = first_last_words(chapter.get("text") or "", 40)
            prompt = USER_A.format(titles=member_titles, first=first, last=last)
        else:
            text = chapter.get("text") or ""
            first, last = first_last_words(text, 40)
            snippet = first if first == last else f"{first}\n...\n{last}"
            prompt = USER_PLAIN.format(text=snippet or text[:800])
        title, raw, runtime = title_one(llm, prompt)
        if (
            chapter["start"] != locked["start"]
            or chapter["end"] != locked["end"]
            or list(chapter.get("source_ids") or chapter["leaf_ids"]) != locked["source_ids"]
        ):
            raise RuntimeError("title step attempted to change boundaries")
        chapter["title"] = title
        rows.append(
            {
                "id": chapter["id"],
                "title": title,
                "raw_title": raw,
                "llm_runtime_sec": runtime,
                "start": locked["start"],
                "end": locked["end"],
                "source_ids": locked["source_ids"],
            }
        )
        write_json(LLM_DIR / out_name, {"per_chapter": rows})
    payload["titles_applied"] = True
    payload["chapters"] = chapters
    write_json(chapters_path, payload)
    write_json(LLM_DIR / out_name, {"execution_mode": "local", "provider": "llama.cpp", "per_chapter": rows})
    write_json(
        OUT_DIR / review_name,
        {"experiment": payload.get("experiment"), "rows": review_sheet(chapters, method)},
    )
    return {"n": len(rows), "titles": [row["title"] for row in rows]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--target", required=True, choices=["a", "c", "d", "c_after_merge"])
    args = parser.parse_args()
    llm = Llama(
        model_path=str(args.model),
        n_ctx=4096,
        n_threads=args.threads,
        n_threads_batch=args.threads,
        n_batch=256,
        verbose=False,
    )
    if args.target == "a":
        result = apply_titles(
            OUT_DIR / "exp_a_chapters.json",
            llm,
            mode="a",
            out_name="exp_a_titles.json",
            review_name="review_sheet_a.json",
            method="title_embed_adjacent",
        )
    elif args.target == "c":
        result = apply_titles(
            OUT_DIR / "exp_c_chapters.json",
            llm,
            mode="plain",
            out_name="exp_c_titles.json",
            review_name="review_sheet_c.json",
            method="pack_across_speakers",
        )
    elif args.target == "c_after_merge":
        result = apply_titles(
            OUT_DIR / "exp_c_chapters.json",
            llm,
            mode="a",
            out_name="exp_c_titles_after_merge.json",
            review_name="review_sheet_c.json",
            method="pack_across_speakers",
        )
    else:
        result = apply_titles(
            OUT_DIR / "exp_d_chapters.json",
            llm,
            mode="plain",
            out_name="exp_d_titles.json",
            review_name="review_sheet_d.json",
            method="late_chunking",
        )
    print(json.dumps({"target": args.target, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()

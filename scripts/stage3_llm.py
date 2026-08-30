#!/usr/bin/env python3
"""Stage 3: extract key points then titles from frozen C/D chapters.

One local model (Qwen3-8B Q5_K_M). Never edits id/start/end/source_ids/speakers.
P1 = one-shot JSON. P2 = points first, title from those lists only.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from llama_cpp import Llama

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stage2b_common import clip_title, write_json  # noqa: E402

CHAPTERS_D = ROOT / "results" / "chunking" / "2b" / "exp_d_chapters.json"
CHAPTERS_C = ROOT / "results" / "chunking" / "2b" / "exp_c_chapters.json"
OUT_DIR = ROOT / "results" / "llm" / "3"

THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)
FORBIDDEN_OPEN = re.compile(
    r"^\s*(обсудили|говорили о|совещание по|обсуждение)\b",
    re.I,
)

SYSTEM = (
    "Ты секретарь русскоязычного совещания. Пиши только то, что явно сказано в тексте. "
    "Не выдумывай людей, числа, решения, поручения и сроки. "
    "Не пиши общие фразы вроде «обсудили», «говорили о», «совещание по», «обсуждение». "
    "Каждый пункт — проверяемое утверждение: кто/что/цифра/решение/условие. "
    "Пустой список обязателен, если факта нет. Не указывай и не меняй время. "
    "Отвечай только JSON без markdown."
)

P1_USER = (
    "/no_think\n"
    "По тексту главы верни ОДИН JSON-объект без markdown со схемой:\n"
    "{{\n"
    '  "title": "краткий заголовок не больше 10 русских слов, по фактам, без слова Обсуждение",\n'
    '  "key_points": ["от 2 до 6 конкретных тезисов"],\n'
    '  "actions": ["поручения и следующие шаги только если они есть в тексте"],\n'
    '  "open_questions": ["неснятые вопросы только если они есть в тексте"],\n'
    '  "asr_notes": ["подозрение на ошибку распознавания, иначе пустой список"]\n'
    "}}\n"
    "Запрещены начала пунктов: обсудили, говорили о, совещание по, обсуждение.\n"
    "Не копируй таймкоды. Не пиши ничего кроме JSON.\n\n"
    "ТЕКСТ:\n{text}"
)

P2_POINTS_USER = (
    "/no_think\n"
    "По тексту главы верни ОДИН JSON-объект без markdown ТОЛЬКО с полями:\n"
    "{{\n"
    '  "key_points": ["от 2 до 6 конкретных тезисов: решение, цифра, условие, договорённость"],\n'
    '  "actions": ["поручения и следующие шаги только если они есть в тексте"],\n'
    '  "open_questions": ["неснятые вопросы только если они есть в тексте"],\n'
    '  "asr_notes": ["подозрение на ошибку распознавания, иначе пустой список"]\n'
    "}}\n"
    "Поля title нет. Запрещены начала пунктов: обсудили, говорили о, совещание по, обсуждение.\n"
    "Пустые списки обязательны, если фактов нет. Не пиши ничего кроме JSON.\n\n"
    "ТЕКСТ:\n{text}"
)

P2_TITLE_USER = (
    "/no_think\n"
    "По списку пунктов дай ТОЛЬКО JSON вида {{\"title\":\"...\"}}.\n"
    "Заголовок не больше 10 русских слов, конкретный, из пунктов, без слова Обсуждение.\n"
    "Не добавляй факты, которых нет в пунктах. Не пиши ничего кроме JSON.\n\n"
    "ПУНКТЫ:\n{lists}"
)


def frozen_meta(chapter: dict[str, Any]) -> dict[str, Any]:
    source_ids = list(chapter.get("source_ids") or chapter.get("leaf_ids") or [])
    return {
        "id": chapter["id"],
        "start": chapter["start"],
        "end": chapter["end"],
        "source_ids": source_ids,
        "speakers": list(chapter.get("speakers") or []),
    }


def assert_frozen(chapter: dict[str, Any], out: dict[str, Any]) -> None:
    locked = frozen_meta(chapter)
    if (
        out["id"] != locked["id"]
        or out["start"] != locked["start"]
        or out["end"] != locked["end"]
        or list(out["source_ids"]) != locked["source_ids"]
        or list(out.get("speakers") or []) != locked["speakers"]
    ):
        raise RuntimeError(f"chapter {chapter['id']} metadata mutated")


def strip_think(text: str) -> str:
    cleaned = THINK_RE.sub("", text or "")
    cleaned = FENCE_RE.sub("", cleaned.strip())
    return cleaned.strip()


def extract_json_object(raw: str) -> dict[str, Any] | None:
    text = strip_think(raw)
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = value
    else:
        return []
    out: list[str] = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip()
        if text:
            out.append(text)
    return out


def parse_points(raw: str) -> dict[str, Any] | None:
    parsed = extract_json_object(raw)
    if parsed is None:
        return None
    if not any(key in parsed for key in ("key_points", "actions", "open_questions", "asr_notes")):
        return None
    points = as_str_list(parsed.get("key_points"))
    if len(points) > 6:
        points = points[:6]
    return {
        "key_points": points,
        "actions": as_str_list(parsed.get("actions")),
        "open_questions": as_str_list(parsed.get("open_questions")),
        "asr_notes": as_str_list(parsed.get("asr_notes")),
    }


def parse_title(raw: str) -> str | None:
    parsed = extract_json_object(raw)
    if parsed is None:
        title = clip_title(strip_think(raw))
        return title or None
    if "title" not in parsed:
        return None
    return clip_title(str(parsed.get("title") or ""))


def parse_oneshot(raw: str) -> dict[str, Any] | None:
    parsed = extract_json_object(raw)
    if parsed is None:
        return None
    points = parse_points(json.dumps(parsed, ensure_ascii=False))
    if points is None:
        return None
    title = clip_title(str(parsed.get("title") or ""))
    return {"title": title, **points}


def empty_points() -> dict[str, Any]:
    return {
        "title": "",
        "key_points": [],
        "actions": [],
        "open_questions": [],
        "asr_notes": [],
    }


def load_llm(model: Path, threads: int) -> Llama:
    return Llama(
        model_path=str(model),
        n_ctx=4096,
        n_threads=threads,
        n_threads_batch=threads,
        n_batch=256,
        verbose=False,
    )


def chat(
    llm: Llama,
    user: str,
    *,
    max_tokens: int,
) -> tuple[str, float]:
    started = time.monotonic()
    response = llm.create_chat_completion(
        messages=[
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": user},
        ],
        max_tokens=max_tokens,
        temperature=0.1,
        top_p=0.9,
    )
    raw = (response["choices"][0]["message"]["content"] or "").strip()
    return raw, round(time.monotonic() - started, 3)


def chapter_row(chapter: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    row = {
        **frozen_meta(chapter),
        "title": fields.get("title") or "",
        "key_points": list(fields.get("key_points") or []),
        "actions": list(fields.get("actions") or []),
        "open_questions": list(fields.get("open_questions") or []),
        "asr_notes": list(fields.get("asr_notes") or []),
    }
    assert_frozen(chapter, row)
    return row


def load_chapters(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    chapters = payload.get("chapters") or []
    if not chapters:
        raise SystemExit(f"no chapters in {path}")
    return chapters


def resume_done(out_path: Path, *, retry_failed: bool = False) -> dict[int, dict[str, Any]]:
    if not out_path.exists():
        return {}
    previous = json.loads(out_path.read_text(encoding="utf-8"))
    done: dict[int, dict[str, Any]] = {}
    for row in previous.get("chapters") or []:
        cid = int(row["id"])
        parse_ok = bool(row.get("parse_ok"))
        if retry_failed and not parse_ok:
            continue
        if parse_ok or row.get("key_points") or row.get("title"):
            done[cid] = row
    return done


def ordered_rows(source_chapters: list[dict[str, Any]], by_id: dict[int, dict[str, Any]]) -> list[dict[str, Any]]:
    return [by_id[int(chapter["id"])] for chapter in source_chapters if int(chapter["id"]) in by_id]


def write_run(
    out_path: Path,
    *,
    prompt_id: str,
    input_artifact: str,
    model_name: str,
    chapters: list[dict[str, Any]],
    calls: list[dict[str, Any]],
    started: float,
    extra: dict[str, Any] | None = None,
) -> None:
    payload = {
        "execution_mode": "local",
        "provider": "llama.cpp",
        "model": model_name,
        "prompt_id": prompt_id,
        "input_artifact": input_artifact,
        "llm_runtime_sec": round(sum(float(row.get("llm_runtime_sec") or 0) for row in chapters), 3),
        "this_run_sec": round(time.monotonic() - started, 3),
        "chapters": chapters,
        "calls": calls,
    }
    if extra:
        payload.update(extra)
    write_json(out_path, payload)


def run_p1(
    llm: Llama,
    chapters: list[dict[str, Any]],
    out_path: Path,
    model_name: str,
    input_artifact: str,
    *,
    retry_failed: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    by_id: dict[int, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    if out_path.exists():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        for row in prev.get("chapters") or []:
            by_id[int(row["id"])] = row
        calls = list(prev.get("calls") or [])
    done = resume_done(out_path, retry_failed=retry_failed)
    for chapter in chapters:
        cid = int(chapter["id"])
        if cid in done:
            continue
        raw = ""
        runtime = 0.0
        parsed = None
        retries = 0
        for attempt in range(2):
            raw, runtime = chat(llm, P1_USER.format(text=chapter.get("text") or ""), max_tokens=640)
            parsed = parse_oneshot(raw)
            retries = attempt
            if parsed is not None:
                break
        fields = parsed or empty_points()
        row = chapter_row(chapter, fields)
        row["llm_runtime_sec"] = runtime
        row["parse_ok"] = parsed is not None
        row["retries"] = retries
        by_id[cid] = row
        calls = [item for item in calls if int(item.get("id")) != cid]
        calls.append(
            {
                "id": chapter["id"],
                "pass": "oneshot",
                "llm_runtime_sec": runtime,
                "parse_ok": parsed is not None,
                "retries": retries,
                "raw": raw,
            }
        )
        write_run(
            out_path,
            prompt_id="P1",
            input_artifact=input_artifact,
            model_name=model_name,
            chapters=ordered_rows(chapters, by_id),
            calls=calls,
            started=started,
        )
        print(
            json.dumps(
                {
                    "prompt": "P1",
                    "id": chapter["id"],
                    "parse_ok": parsed is not None,
                    "sec": runtime,
                    "title": row["title"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    rows = ordered_rows(chapters, by_id)
    write_run(
        out_path,
        prompt_id="P1",
        input_artifact=input_artifact,
        model_name=model_name,
        chapters=rows,
        calls=calls,
        started=started,
    )
    return {"n": len(rows), "llm_runtime_sec": round(sum(float(r.get("llm_runtime_sec") or 0) for r in rows), 3)}


def run_p2(
    llm: Llama,
    chapters: list[dict[str, Any]],
    out_path: Path,
    model_name: str,
    input_artifact: str,
    *,
    retry_failed: bool = False,
) -> dict[str, Any]:
    started = time.monotonic()
    by_id: dict[int, dict[str, Any]] = {}
    calls: list[dict[str, Any]] = []
    if out_path.exists():
        prev = json.loads(out_path.read_text(encoding="utf-8"))
        for row in prev.get("chapters") or []:
            by_id[int(row["id"])] = row
        calls = list(prev.get("calls") or [])
    done = resume_done(out_path, retry_failed=retry_failed)
    for chapter in chapters:
        cid = int(chapter["id"])
        if cid in done:
            continue
        raw_points = ""
        runtime_points = 0.0
        parsed = None
        retries = 0
        for attempt in range(2):
            raw_points, runtime_points = chat(
                llm,
                P2_POINTS_USER.format(text=chapter.get("text") or ""),
                max_tokens=640,
            )
            parsed = parse_points(raw_points)
            retries = attempt
            if parsed is not None:
                break
        title = ""
        raw_title = ""
        runtime_title = 0.0
        title_skipped = parsed is None
        if parsed is not None:
            lists = json.dumps(
                {
                    "key_points": parsed["key_points"],
                    "actions": parsed["actions"],
                    "open_questions": parsed["open_questions"],
                    "asr_notes": parsed["asr_notes"],
                },
                ensure_ascii=False,
                indent=2,
            )
            raw_title, runtime_title = chat(
                llm,
                P2_TITLE_USER.format(lists=lists),
                max_tokens=80,
            )
            title = parse_title(raw_title) or ""
            fields = {**parsed, "title": title}
        else:
            fields = empty_points()
        row = chapter_row(chapter, fields)
        row["llm_runtime_sec"] = round(runtime_points + runtime_title, 3)
        row["llm_runtime_points_sec"] = runtime_points
        row["llm_runtime_title_sec"] = runtime_title
        row["parse_ok"] = parsed is not None
        row["retries"] = retries
        row["title_skipped"] = title_skipped
        by_id[cid] = row
        calls = [item for item in calls if int(item.get("id")) != cid]
        calls.append(
            {
                "id": chapter["id"],
                "pass": "points",
                "llm_runtime_sec": runtime_points,
                "parse_ok": parsed is not None,
                "retries": retries,
                "raw": raw_points,
            }
        )
        if not title_skipped:
            calls.append(
                {
                    "id": chapter["id"],
                    "pass": "title",
                    "llm_runtime_sec": runtime_title,
                    "parse_ok": bool(title),
                    "retries": 0,
                    "raw": raw_title,
                }
            )
        write_run(
            out_path,
            prompt_id="P2",
            input_artifact=input_artifact,
            model_name=model_name,
            chapters=ordered_rows(chapters, by_id),
            calls=calls,
            started=started,
        )
        print(
            json.dumps(
                {
                    "prompt": "P2",
                    "id": chapter["id"],
                    "parse_ok": parsed is not None,
                    "sec": row["llm_runtime_sec"],
                    "title": row["title"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
    rows = ordered_rows(chapters, by_id)
    write_run(
        out_path,
        prompt_id="P2",
        input_artifact=input_artifact,
        model_name=model_name,
        chapters=rows,
        calls=calls,
        started=started,
    )
    return {"n": len(rows), "llm_runtime_sec": round(sum(float(r.get("llm_runtime_sec") or 0) for r in rows), 3)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--phase", required=True, choices=["p1_d", "p2_d", "p_winner_c"])
    parser.add_argument("--winner", choices=["p1", "p2"], default=None)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    if args.phase == "p_winner_c" and args.winner is None:
        raise SystemExit("--winner p1|p2 is required for p_winner_c")

    llm = load_llm(args.model, args.threads)
    model_name = args.model.name

    if args.phase == "p1_d":
        if not CHAPTERS_D.exists():
            raise SystemExit("D chapters missing; stop. Do not rebuild chapters.")
        result = run_p1(
            llm,
            load_chapters(CHAPTERS_D),
            OUT_DIR / "p1_d.json",
            model_name,
            "results/chunking/2b/exp_d_chapters.json",
            retry_failed=args.retry_failed,
        )
    elif args.phase == "p2_d":
        if not CHAPTERS_D.exists():
            raise SystemExit("D chapters missing; stop. Do not rebuild chapters.")
        result = run_p2(
            llm,
            load_chapters(CHAPTERS_D),
            OUT_DIR / "p2_d.json",
            model_name,
            "results/chunking/2b/exp_d_chapters.json",
            retry_failed=args.retry_failed,
        )
    elif args.winner == "p1":
        result = run_p1(
            llm,
            load_chapters(CHAPTERS_C),
            OUT_DIR / "p_winner_c.json",
            model_name,
            "results/chunking/2b/exp_c_chapters.json",
            retry_failed=args.retry_failed,
        )
        payload = json.loads((OUT_DIR / "p_winner_c.json").read_text(encoding="utf-8"))
        payload["prompt_id"] = "P1"
        payload["winner_from_d"] = "P1"
        write_json(OUT_DIR / "p_winner_c.json", payload)
    else:
        result = run_p2(
            llm,
            load_chapters(CHAPTERS_C),
            OUT_DIR / "p_winner_c.json",
            model_name,
            "results/chunking/2b/exp_c_chapters.json",
            retry_failed=args.retry_failed,
        )
        payload = json.loads((OUT_DIR / "p_winner_c.json").read_text(encoding="utf-8"))
        payload["prompt_id"] = "P2"
        payload["winner_from_d"] = "P2"
        write_json(OUT_DIR / "p_winner_c.json", payload)

    print(json.dumps({"phase": args.phase, **result}, ensure_ascii=False))


if __name__ == "__main__":
    main()

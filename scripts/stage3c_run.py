#!/usr/bin/env python3
"""Stage 3c: independent Gemini and local Qwen extract+summary into two folders."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asr_json_to_md import fmt_ts, parse_md_utterances  # noqa: E402
from stage3b_insights import (  # noqa: E402
    GEMINI_MODELS,
    GEMINI_TRIES,
    NVIDIA_MODELS,
    NVIDIA_TRIES,
    call_gemini,
    call_nvidia,
    redact,
    sleep_backoff,
)
from stage3c_pack import (  # noqa: E402
    CHAPTERS_JSON,
    TRANSCRIPT,
    overlap,
    slice_chapter,
    write_slices,
)

OUT = ROOT / "results" / "llm" / "3c"
DISCUSSION_RE = re.compile(r"^\s*(обсуждение|совещание по|говорили о|обсудили)\b", re.I)
FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*|\s*```$", re.I | re.M)
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
SRC_LINE = re.compile(r"src:\s*(\[[^\]]+\])")
BULLET = re.compile(r"^-\s+(?!\s*kind:)(.+)$")
TITLE_LINE = re.compile(r"^#{1,3}\s+(?:D\d{2}\s+[—-]\s+)?(.+)$")
FULL_SPAN = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2})")
ONE_TS = re.compile(r"(\d{2}:\d{2}:\d{2}\.\d{2})")
SHORT_SPAN = re.compile(r"(\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}\.\d{2})")
SPEAKER_RE = re.compile(r"SPEAKER_[A-Z0-9]+")


def strip_model_text(text: str) -> str:
    text = THINK_RE.sub("", text)
    text = FENCE_RE.sub("", text)
    return text.strip()


def load_chapters() -> list[dict[str, Any]]:
    return json.loads(CHAPTERS_JSON.read_text(encoding="utf-8"))["chapters"]


def load_utterances() -> list[dict[str, Any]]:
    return parse_md_utterances(TRANSCRIPT)


def chapter_utterances(chapter: dict[str, Any], utterances: list[dict[str, Any]]) -> list[tuple[str, str]]:
    rows = []
    for row in utterances:
        if overlap(row["start"], row["end"], chapter):
            label = f"[{fmt_ts(row['start'])}-{fmt_ts(row['end'])} | {row['speaker']}]"
            rows.append((label, row["text"]))
    return rows


def allowed_labels(chapter: dict[str, Any], utterances: list[dict[str, Any]]) -> list[str]:
    return [label for label, _text in chapter_utterances(chapter, utterances)]


def _pick_by_speaker(hits: list[str], src: str) -> str | None:
    if not hits:
        return None
    speaker = SPEAKER_RE.search(src)
    if speaker:
        for label in hits:
            if speaker.group(0) in label:
                return label
    return hits[0]


def match_src(
    src: str,
    allowed: list[str],
    texts: dict[str, str] | None = None,
) -> str | None:
    got = src.strip()
    if not got.startswith("["):
        got = f"[{got}"
    if not got.endswith("]"):
        got = f"{got}]"
    if got in allowed:
        return got
    times = FULL_SPAN.search(got)
    if times:
        hits = [label for label in allowed if times.group(0) in label]
        picked = _pick_by_speaker(hits, got)
        if picked:
            return picked
    one = ONE_TS.search(got)
    if one:
        hits = [label for label in allowed if one.group(1) in label]
        picked = _pick_by_speaker(hits, got)
        if picked:
            return picked
    short = SHORT_SPAN.search(got)
    if short:
        start_tail = short.group(1).split(":")[-1]
        end_tail = short.group(2).split(":")[-1]
        hits = []
        for label in allowed:
            span = FULL_SPAN.search(label)
            if not span:
                continue
            if span.group(1).endswith(start_tail) and span.group(2).endswith(end_tail):
                hits.append(label)
        picked = _pick_by_speaker(hits, got)
        if picked:
            return picked
    needle = re.sub(r"\s+", " ", got.strip("[]").strip())
    if texts and len(needle) >= 20:
        scored: list[tuple[int, str]] = []
        for label, text in texts.items():
            body = re.sub(r"\s+", " ", text)
            if needle in body:
                scored.append((len(body), label))
            elif len(body) >= 20 and body in needle:
                scored.append((len(body), label))
        if scored:
            scored.sort(reverse=True)
            return scored[0][1]
    return None


def extract_prompt(chapter: dict[str, Any], chunk: str) -> str:
    return (
        "Ты секретарь русскоязычного совещания. Из ОДНОЙ главы извлеки только устойчивые инсайты.\n"
        "Пиши только то, что явно сказано. Не выдумывай людей, числа, сроки, решения.\n"
        "Не исправляй ASR в новое число. Не копируй реплику дословно как тезис — перескажи смысл.\n\n"
        "Инсайт пиши ТОЛЬКО если верно одно:\n"
        "— тема звучит в двух-трёх репликах, не в одной случайной фразе;\n"
        "— это вопрос и ответ (ответ может быть отложен);\n"
        "— есть развилка / две точки зрения.\n"
        "Не бери приветствия, роли («мы как инвесторы»), мусор ASR, цифру без продолжения.\n"
        "Если в главе только обрывки (нет законченной мысли на 2–3 реплики) — заголовок как общий смысл, после clock ровно: нет инсайтов\n"
        "Не вытягивай инсайт из крошек вроде «приезжающий застройку».\n\n"
        "Формат, без вступления и без markdown-ограждений:\n"
        f"# короткий заголовок ≤8 русских слов (не «Обсуждение», не «Совещание по»)\n"
        f"clock: {chapter['clock']}\n"
        "- тезис одной строкой\n"
        "  src: [целиком метка из строки реплики]\n\n"
        f"clock скопируй БЕЗ ИЗМЕНЕНИЙ: {chapter['clock']}\n"
        "src — квадратные скобки из входа. Время не выдумывай.\n\n"
        f"ГЛАВА {chapter['id']}:\n{chunk}\n"
    )


def summary_prompt(insights: str) -> str:
    return (
        "По готовым инсайтам совещания напиши саммари. Не выдумывай факты и числа.\n"
        "Не тащи все пункты глав — только те, что тянут встречу (2–3 реплики / вопрос-ответ / развилка).\n"
        "Это рабочее совещание, часто без жёстких решений; тихие куски ASR шумные — скажи это в оценке, если видно.\n\n"
        "Формат, без вступления:\n"
        "# Саммари\n"
        "## Оценка\n"
        "(2–5 предложений: характер встречи, шум ASR, были ли решения)\n"
        "## Ключевые инсайты\n"
        "- короткие тезисы\n\n"
        "ИНСАЙТЫ:\n"
        f"{insights}\n"
    )


def parse_extract(
    raw: str,
    chapter: dict[str, Any],
    allowed: list[str],
    texts: dict[str, str] | None = None,
) -> dict[str, Any]:
    text = strip_model_text(raw)
    title = chapter["id"]
    bullets: list[dict[str, str]] = []
    empty = False
    pending: str | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.lower() == "нет инсайтов":
            empty = True
            continue
        title_match = TITLE_LINE.match(stripped)
        if title_match and not stripped.lower().startswith("clock:"):
            candidate = title_match.group(1).strip()
            if not candidate.startswith("Главы"):
                title = candidate
            continue
        if stripped.lower().startswith("clock:"):
            continue
        src_match = SRC_LINE.search(stripped)
        if src_match and pending is not None:
            mapped = match_src(src_match.group(1), allowed, texts)
            if mapped:
                bullets.append({"text": pending, "src": mapped})
                pending = None
            continue
        bullet = BULLET.match(stripped)
        if bullet:
            pending = bullet.group(1).strip()
            continue
    if DISCUSSION_RE.search(title):
        title = re.sub(r"^\s*(обсуждение|совещание по)\s+", "", title, flags=re.I).strip() or title
    if empty and not bullets:
        bullets = []
    return {"title": title[:80], "insights": bullets, "empty": not bullets}


def render_insights(chapters: list[dict[str, Any]], parsed: dict[str, dict[str, Any]]) -> str:
    lines = ["# Главы D", ""]
    for chapter in chapters:
        row = parsed[chapter["id"]]
        lines.append(f"### {chapter['id']} — {row['title']}")
        lines.append(f"clock: {chapter['clock']}")
        if row["empty"] or not row["insights"]:
            lines.append("нет инсайтов")
            lines.append("")
            continue
        for item in row["insights"]:
            lines.append(f"- {item['text']}")
            if item.get("src"):
                lines.append(f"  src: {item['src']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def log_error(log_path: Path, attempt: int, provider: str, http_status: int | None, error_class: str, message: str) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "attempt": attempt,
        "provider": provider,
        "http_status": http_status,
        "error_class": error_class,
        "message": redact(message),
    }
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


class ApiClient:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self.gemini_failures = 0
        self.nvidia_failures = 0
        self.provider = "gemini"
        self.model = GEMINI_MODELS[0]
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, *, max_tokens: int, purpose: str) -> str:
        if self.provider == "gemini" and self.gemini_failures < GEMINI_TRIES:
            text = self._try_gemini(prompt, max_tokens, purpose)
            if text:
                return text
        if self.nvidia_failures < NVIDIA_TRIES:
            self.provider = "nvidia"
            text = self._try_nvidia(prompt, max_tokens, purpose)
            if text:
                return text
        raise RuntimeError("both Gemini and NVIDIA exhausted without text")

    def _try_gemini(self, prompt: str, max_tokens: int, purpose: str) -> str | None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self.gemini_failures = GEMINI_TRIES
            log_error(self.log_path, self.gemini_failures, "gemini", None, "MissingCredential", "Gemini API credential is not available")
            return None
        while self.gemini_failures < GEMINI_TRIES:
            model = GEMINI_MODELS[min(self.gemini_failures, len(GEMINI_MODELS) - 1)]
            try:
                started = time.monotonic()
                text, usage = call_gemini(api_key, model, prompt, max_tokens)
                if not text:
                    raise RuntimeError("Gemini returned no text")
                self.provider = "gemini"
                self.model = model
                self.calls.append(
                    {
                        "purpose": purpose,
                        "provider": "gemini",
                        "model": model,
                        "runtime_sec": round(time.monotonic() - started, 3),
                        "usage": usage,
                    }
                )
                return text
            except Exception as exc:
                self.gemini_failures += 1
                log_error(
                    self.log_path,
                    self.gemini_failures,
                    "gemini",
                    getattr(exc, "http_status", None),
                    type(exc).__name__,
                    str(exc),
                )
                if self.gemini_failures < GEMINI_TRIES:
                    sleep_backoff(self.gemini_failures - 1)
        return None

    def _try_nvidia(self, prompt: str, max_tokens: int, purpose: str) -> str | None:
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            self.nvidia_failures = NVIDIA_TRIES
            log_error(self.log_path, self.nvidia_failures, "nvidia", None, "MissingCredential", "NVIDIA API credential is not available")
            return None
        while self.nvidia_failures < NVIDIA_TRIES:
            model = NVIDIA_MODELS[min(self.nvidia_failures, len(NVIDIA_MODELS) - 1)]
            try:
                started = time.monotonic()
                text, usage = call_nvidia(api_key, model, prompt, max_tokens)
                if not text:
                    raise RuntimeError("NVIDIA returned no text")
                self.provider = "nvidia"
                self.model = model
                self.calls.append(
                    {
                        "purpose": purpose,
                        "provider": "nvidia",
                        "model": model,
                        "runtime_sec": round(time.monotonic() - started, 3),
                        "usage": usage,
                    }
                )
                return text
            except Exception as exc:
                self.nvidia_failures += 1
                log_error(
                    self.log_path,
                    self.nvidia_failures,
                    "nvidia",
                    getattr(exc, "http_status", None),
                    type(exc).__name__,
                    str(exc),
                )
                if self.nvidia_failures < NVIDIA_TRIES:
                    sleep_backoff(self.nvidia_failures - 1)
        return None


class LocalClient:
    def __init__(self, model: Path, threads: int, n_ctx: int) -> None:
        from llama_cpp import Llama

        started = time.monotonic()
        self.llm = Llama(
            model_path=str(model),
            n_ctx=n_ctx,
            n_threads=threads,
            n_threads_batch=threads,
            n_batch=256,
            verbose=False,
        )
        self.load_sec = round(time.monotonic() - started, 3)
        self.provider = "local"
        self.model = model.name
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, *, max_tokens: int, purpose: str) -> str:
        started = time.monotonic()
        user = prompt if prompt.lstrip().startswith("/no_think") else "/no_think\n" + prompt
        response = self.llm.create_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты секретарь русскоязычного совещания. "
                        "Пиши только то, что явно сказано. Не выдумывай числа и людей."
                    ),
                },
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=0.1,
            top_p=0.9,
        )
        text = (response["choices"][0]["message"]["content"] or "").strip()
        self.calls.append(
            {
                "purpose": purpose,
                "provider": "local",
                "model": self.model,
                "runtime_sec": round(time.monotonic() - started, 3),
            }
        )
        return text


def run_provider(name: str, client: Any, chapters: list[dict[str, Any]], utterances: list[dict[str, Any]]) -> None:
    dest = OUT / name
    dest.mkdir(parents=True, exist_ok=True)
    parsed: dict[str, dict[str, Any]] = {}
    for chapter in chapters:
        chunk = slice_chapter(utterances, chapter)
        rows = chapter_utterances(chapter, utterances)
        allowed = [label for label, _text in rows]
        texts = {label: text for label, text in rows}
        raw = client.complete(
            extract_prompt(chapter, chunk),
            max_tokens=1024,
            purpose=f"extract-{chapter['id']}",
        )
        (dest / "raw").mkdir(exist_ok=True)
        (dest / "raw" / f"{chapter['id']}.txt").write_text(raw, encoding="utf-8")
        parsed[chapter["id"]] = parse_extract(raw, chapter, allowed, texts)
    insights = render_insights(chapters, parsed)
    (dest / "insights.md").write_text(insights, encoding="utf-8")
    summary_raw = client.complete(summary_prompt(insights), max_tokens=2048, purpose="summary")
    (dest / "raw" / "summary.txt").write_text(summary_raw, encoding="utf-8")
    summary = strip_model_text(summary_raw)
    if not summary.lstrip().startswith("#"):
        summary = "# Саммари\n\n" + summary
    (dest / "summary.md").write_text(summary.rstrip() + "\n", encoding="utf-8")
    meta = {
        "provider": getattr(client, "provider", name),
        "model": getattr(client, "model", name),
        "calls": getattr(client, "calls", []),
        "n_chapters": len(chapters),
        "n_insights": sum(len(row["insights"]) for row in parsed.values()),
    }
    if hasattr(client, "load_sec"):
        meta["load_sec"] = client.load_sec
    (dest / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"folder": name, **{k: meta[k] for k in ("provider", "model", "n_insights")}}, ensure_ascii=False))


def rerender_from_raw(name: str, chapters: list[dict[str, Any]], utterances: list[dict[str, Any]]) -> None:
    dest = OUT / name
    raw_dir = dest / "raw"
    parsed: dict[str, dict[str, Any]] = {}
    for chapter in chapters:
        raw_path = raw_dir / f"{chapter['id']}.txt"
        if not raw_path.is_file():
            raise SystemExit(f"missing {raw_path}")
        rows = chapter_utterances(chapter, utterances)
        allowed = [label for label, _text in rows]
        texts = {label: text for label, text in rows}
        parsed[chapter["id"]] = parse_extract(
            raw_path.read_text(encoding="utf-8"), chapter, allowed, texts
        )
    insights = render_insights(chapters, parsed)
    (dest / "insights.md").write_text(insights, encoding="utf-8")
    meta_path = dest / "run.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
    meta["n_insights"] = sum(len(row["insights"]) for row in parsed.values())
    meta["rerendered"] = True
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"folder": name, "rerender": True, "n_insights": meta["n_insights"]}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("gemini", "local", "both"), default="gemini")
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "Qwen3-8B-Q5_K_M.gguf")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--n-ctx", type=int, default=8192)
    parser.add_argument("--rerender", action="store_true", help="reparse raw chapter extracts; no model calls")
    args = parser.parse_args()
    if not TRANSCRIPT.is_file() or not CHAPTERS_JSON.is_file():
        raise SystemExit("missing data/3c_data/transcript.md or chapters.json; run python scripts/stage3c_pack.py")
    chapters = load_chapters()
    utterances = load_utterances()
    write_slices(utterances, chapters)
    OUT.mkdir(parents=True, exist_ok=True)
    if args.rerender:
        targets = ["gemini", "local"] if args.provider == "both" else [args.provider]
        for name in targets:
            rerender_from_raw(name, chapters, utterances)
        return
    if args.provider in ("gemini", "both"):
        client = ApiClient(OUT / "gemini" / "api_errors.jsonl")
        run_provider("gemini", client, chapters, utterances)
    if args.provider in ("local", "both"):
        if not args.model.is_file():
            dest = OUT / "local"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "summary.md").write_text(
                f"# Саммари\n\nfailure_kind: install\n\nmissing GGUF: {args.model}\n",
                encoding="utf-8",
            )
            raise SystemExit(2)
        local = None
        last_error: Exception | None = None
        for _attempt in range(2):
            try:
                local = LocalClient(args.model, args.threads, args.n_ctx)
                break
            except Exception as exc:
                last_error = exc
        if local is None:
            dest = OUT / "local"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "summary.md").write_text(
                f"# Саммари\n\nfailure_kind: install\n\n{type(last_error).__name__}: {last_error}\n",
                encoding="utf-8",
            )
            raise SystemExit(2)
        run_provider("local", local, chapters, utterances)


if __name__ == "__main__":
    main()

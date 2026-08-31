#!/usr/bin/env python3
"""Stage 3b: per-chapter markdown insights, one report, groundedness self-check.

API first (Gemini, then NVIDIA). Never logs credentials or Authorization headers.
Does not read eval/ or .env. Does not overwrite results/asr/2 or results/llm/3.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHUNKS_DIR = ROOT / "data" / "3b_data" / "chunks_d"
OUT_DIR = ROOT / "results" / "llm" / "3b"
INSIGHTS_DIR = OUT_DIR / "insights_d"
ERROR_LOG = OUT_DIR / "api_errors.jsonl"

KINDS = {
    "question",
    "answer",
    "fact",
    "number",
    "problem",
    "action",
    "owner",
    "deadline",
}
CHAPTER_IDS = [f"D{i:02d}" for i in range(12)]
SRC_RE = re.compile(r"\[(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2}) \| [A-Z0-9_]+(?: \| [CD]\d{2})?\]")
TITLE_RE = re.compile(r"^#\s+(.+)$", re.M)
CLOCK_RE = re.compile(r"<!--\s*clock_json:\s*([^\s]+)\s*-->")
CHAPTER_RE = re.compile(r"<!--\s*chapter:\s*(\S+)\s*-->")
FENCE_RE = re.compile(r"^```(?:markdown|md)?\s*|\s*```$", re.I | re.M)
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
DISCUSSION_RE = re.compile(r"^\s*(обсуждение|совещание по|говорили о|обсудили)\b", re.I)
GEMINI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-flash-latest",
    "gemini-2.5-pro",
]
NVIDIA_MODELS = [
    "meta/llama-3.1-70b-instruct",
    "qwen/qwen2.5-72b-instruct",
    "nvidia/llama-3.1-nemotron-70b-instruct",
    "meta/llama-3.3-70b-instruct",
    "qwen/qwen2.5-7b-instruct",
]
GEMINI_TRIES = 5
NVIDIA_TRIES = 5


def redact(text: str) -> str:
    """Strip secrets from an error string. Never keep query keys or Bearer tokens."""
    cleaned = str(text)
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "NVIDIA_API_KEY", "HF_TOKEN"):
        value = os.environ.get(name)
        if value:
            cleaned = cleaned.replace(value, "REDACTED")
    cleaned = re.sub(r"(key=)[^&\s\"']+", r"\1REDACTED", cleaned, flags=re.I)
    cleaned = re.sub(r"(Bearer\s+)\S+", r"\1REDACTED", cleaned, flags=re.I)
    cleaned = re.sub(r"(Authorization:\s*)\S+", r"\1REDACTED", cleaned, flags=re.I)
    cleaned = re.sub(r"(api[_-]?key[\"']?\s*[:=]\s*[\"']?)[^\"'\s,]+", r"\1REDACTED", cleaned, flags=re.I)
    return cleaned


def log_error(attempt: int, provider: str, http_status: int | None, error_class: str, message: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    row = {
        "attempt": attempt,
        "provider": provider,
        "http_status": http_status,
        "error_class": error_class,
        "message": redact(message),
    }
    with ERROR_LOG.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def sleep_backoff(try_index: int) -> None:
    delay = min(10.0, 2.0 * (2 ** try_index))
    delay = min(10.0, max(2.0, delay))
    time.sleep(delay + random.uniform(0.0, 0.4))


def html_comment(path: Path, name: str) -> str | None:
    pattern = re.compile(rf"<!--\s*{re.escape(name)}:\s*(.*?)\s*-->")
    match = pattern.search(path.read_text(encoding="utf-8"))
    return match.group(1).strip() if match else None


def utterance_labels(text: str) -> list[str]:
    return [match.group(0) for match in SRC_RE.finditer(text)]


def strip_model_text(text: str) -> str:
    cleaned = THINK_RE.sub("", text).strip()
    cleaned = FENCE_RE.sub("", cleaned).strip()
    return cleaned


def parse_insights(raw: str) -> tuple[str, list[dict[str, str]], bool]:
    """Return (title, insights, empty_flag)."""
    text = strip_model_text(raw)
    title_match = TITLE_RE.search(text)
    title = title_match.group(1).strip() if title_match else ""
    empty = bool(re.search(r"^нет инсайтов\s*$", text, re.M | re.I))
    insights: list[dict[str, str]] = []
    block = re.compile(
        r"^-\s*(?:kind:\s*)?([A-Za-z_]+):?\s*\n\s*src:\s*(.+?)\s*\n\s*text:\s*(.+?)\s*$",
        re.M,
    )
    for match in block.finditer(text):
        src_raw = match.group(2).strip()
        bracket = re.search(r"\[.*?\]", src_raw)
        insights.append(
            {
                "kind": match.group(1).strip().lower().rstrip(":"),
                "src": bracket.group(0) if bracket else src_raw,
                "text": match.group(3).strip(),
            }
        )
    return title, insights, empty and not insights


def _label_span(label: str) -> tuple[str, str] | None:
    match = re.search(r"\[(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2})", label)
    if not match:
        return None
    return match.group(1), match.group(2)


def match_src(src: str, allowed: list[str]) -> str | None:
    src = src.strip()
    if src in allowed:
        return src
    bracket = re.search(r"\[.*?\]", src)
    if bracket and bracket.group(0) in allowed:
        return bracket.group(0)
    times = re.search(r"(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2})", src)
    if times:
        for label in allowed:
            if times.group(0) in label:
                return label
        starts = []
        ends = []
        for label in allowed:
            span = _label_span(label)
            if span:
                starts.append(span[0])
                ends.append(span[1])
        if times.group(1) in starts and times.group(2) in ends:
            return src if src.startswith("[") else f"[{times.group(0)}]"
    one = re.search(r"(\d{2}:\d{2}:\d{2}\.\d{2})", src)
    if one:
        for label in allowed:
            span = _label_span(label)
            if span and one.group(1) in span:
                return label
    return None


def render_insight_md(
    title: str,
    chapter: str,
    clock_json: str,
    insights: list[dict[str, str]],
    allowed_srcs: list[str],
    empty: bool,
) -> str:
    lines = [f"# {title}", "", f"<!-- chapter: {chapter} -->", f"<!-- clock_json: {clock_json} -->", ""]
    if empty or not insights:
        lines.append("нет инсайтов")
        lines.append("")
        return "\n".join(lines)
    for row in insights:
        kind = row["kind"] if row["kind"] in KINDS else "fact"
        src = match_src(row["src"], allowed_srcs) or row["src"]
        lines.append(f"- kind: {kind}")
        lines.append(f"  src: {src}")
        lines.append(f"  text: {row['text']}")
        lines.append("")
    return "\n".join(lines)


def extract_prompt(chunk_text: str, chapter: str, unassigned: bool) -> str:
    title_hint = (
        "Заголовок первой строки: `# вне глав` (или синоним ≤8 слов: хвост вне интервалов D)."
        if unassigned
        else "Заголовок первой строки: `# ` + ≤8 русских слов (исход/существительные). Не «Обсуждение …», не «Совещание по»."
    )
    return (
        "Ты секретарь русскоязычного совещания. Из ОДНОЙ главы извлеки инсайты.\n"
        "Пиши только то, что явно сказано в репликах. Не выдумывай людей, числа, сроки, решения.\n"
        "Не исправляй ASR в новое число. owner/deadline только если в строках явно названы.\n\n"
        f"{title_hint}\n"
        "Скопируй без изменений два комментария из входа:\n"
        "<!-- chapter: … -->\n"
        "<!-- clock_json: … -->\n"
        "Дальше список (каждый инсайт три строки):\n"
        "- kind: fact\n"
        "  src: [целиком метка из строки реплики, включая скобки]\n"
        "  text: короткий тезис\n\n"
        f"kind только: {' · '.join(sorted(KINDS))}\n"
        "src — скопируй всю квадратную скобку `[…]` из строки реплики. Не выдумывай время.\n"
        "Если проверяемых тезисов нет — после комментариев напиши ровно: нет инсайтов\n"
        "Без других секций, без markdown-ограждений, без пояснений.\n\n"
        f"ГЛАВА {chapter}:\n{chunk_text}\n"
    )


def assemble_prompt(bundle: str) -> str:
    return (
        "Собери один отчёт совещания из готовых инсайтов по главам D.\n"
        "Не выдумывай главы, факты, числа, ответственных и времена.\n"
        "clock глав бери только из `clock_json` файлов инсайтов. Заголовок главы — из первой строки `# `.\n"
        "Если инсайтов нет (`нет инсайтов`) — главу в «По времени» всё равно укажи, без новых фактов.\n\n"
        "Формат строго такой, без вступления:\n"
        "## Кратко\n"
        "(3–6 предложений по проверяемым тезисам)\n"
        "## Решения\n"
        "(только явно принятое; иначе «не зафиксированы»)\n"
        "## Дальше\n"
        "(только action из инсайтов; иначе «не зафиксированы»)\n"
        "## Открыто\n"
        "(question / problem без ответа; иначе «не зафиксированы»)\n"
        "## По времени\n"
        "### D00 — <title из файла>\n"
        "clock: <clock_json из того файла>\n"
        "- краткие пункты этой главы\n"
        "(далее D01 … D11 в том же виде; `_unassigned` только если там есть инсайты)\n\n"
        "ИНСАЙТЫ:\n"
        f"{bundle}\n"
    )


def self_check_prompt(report: str, transcript: str, clocks: list[str]) -> str:
    clock_list = "\n".join(f"- {item}" for item in clocks)
    return (
        "Проверь отчёт только на выдумки относительно стенограммы и манифеста часов.\n"
        "Не оценивай стиль, полноту, модальность («факт vs цитата vs обещание»).\n"
        "Пересказ того же смысла, что есть в стенограмме — не выдумка.\n"
        "Мусор ASR, скопированный как тезис — не выдумка.\n\n"
        "Перечисли только то, чего НЕТ в стенограмме:\n"
        "1. факты без опоры\n"
        "2. числа, которых нет в тексте (новые цифры, не оговорка ASR)\n"
        "3. clock / интервалы, которых нет в манифесте\n"
        "4. владельцы / ФИО / роли, которых нет в тексте\n\n"
        "Если список пуст — напиши «выдумок нет» по каждому пункту.\n"
        "Коротко, без каталога всех тезисов отчёта.\n"
        "Последняя строка ровно одна из:\n"
        "verdict: usable\n"
        "verdict: not_usable\n"
        "usable = нет новых фактов/чисел/владельцев и все clock из манифеста.\n\n"
        f"МАНИФЕСТ clock_json:\n{clock_list}\n\n"
        f"ОТЧЁТ:\n{report}\n\n"
        f"СТЕНОГРАММА:\n{transcript}\n"
    )


def parse_verdict(text: str) -> str | None:
    match = re.search(r"^verdict:\s*(usable|not_usable)\s*$", strip_model_text(text), re.M | re.I)
    if not match:
        return None
    return match.group(1).lower()


class Stage3bClient:
    def __init__(self) -> None:
        self.gemini_failures = 0
        self.nvidia_failures = 0
        self.provider = "gemini"
        self.model = GEMINI_MODELS[0]
        self.calls: list[dict[str, Any]] = []

    def complete(self, prompt: str, *, max_tokens: int, purpose: str) -> str:
        last_error: Exception | None = None
        if self.provider == "gemini" and self.gemini_failures < GEMINI_TRIES:
            text = self._try_gemini(prompt, max_tokens, purpose)
            if text:
                return text
        if self.nvidia_failures < NVIDIA_TRIES:
            self.provider = "nvidia"
            text = self._try_nvidia(prompt, max_tokens, purpose)
            if text:
                return text
        if last_error:
            raise last_error
        raise RuntimeError("both Gemini and NVIDIA exhausted without text")

    def _try_gemini(self, prompt: str, max_tokens: int, purpose: str) -> str | None:
        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not api_key:
            self.gemini_failures = GEMINI_TRIES
            log_error(self.gemini_failures, "gemini", None, "MissingCredential", "Gemini API credential is not available")
            return None
        while self.gemini_failures < GEMINI_TRIES:
            model = GEMINI_MODELS[min(self.gemini_failures, len(GEMINI_MODELS) - 1)]
            try:
                started = time.monotonic()
                text, usage = call_gemini(api_key, model, prompt, max_tokens)
                runtime = round(time.monotonic() - started, 3)
                if not text:
                    raise RuntimeError("Gemini returned no text")
                self.provider = "gemini"
                self.model = model
                self.calls.append(
                    {
                        "purpose": purpose,
                        "provider": "gemini",
                        "model": model,
                        "runtime_sec": runtime,
                        "usage": usage,
                    }
                )
                return text
            except Exception as exc:
                self.gemini_failures += 1
                status = getattr(exc, "http_status", None)
                log_error(self.gemini_failures, "gemini", status, type(exc).__name__, str(exc))
                if self.gemini_failures < GEMINI_TRIES:
                    sleep_backoff(self.gemini_failures - 1)
        return None

    def _try_nvidia(self, prompt: str, max_tokens: int, purpose: str) -> str | None:
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            self.nvidia_failures = NVIDIA_TRIES
            log_error(self.nvidia_failures, "nvidia", None, "MissingCredential", "NVIDIA API credential is not available")
            return None
        while self.nvidia_failures < NVIDIA_TRIES:
            model = NVIDIA_MODELS[min(self.nvidia_failures, len(NVIDIA_MODELS) - 1)]
            try:
                started = time.monotonic()
                text, usage = call_nvidia(api_key, model, prompt, max_tokens)
                runtime = round(time.monotonic() - started, 3)
                if not text:
                    raise RuntimeError("NVIDIA returned no text")
                self.provider = "nvidia"
                self.model = model
                self.calls.append(
                    {
                        "purpose": purpose,
                        "provider": "nvidia",
                        "model": model,
                        "runtime_sec": runtime,
                        "usage": usage,
                    }
                )
                return text
            except Exception as exc:
                self.nvidia_failures += 1
                status = getattr(exc, "http_status", None)
                log_error(self.nvidia_failures, "nvidia", status, type(exc).__name__, str(exc))
                if self.nvidia_failures < NVIDIA_TRIES:
                    sleep_backoff(self.nvidia_failures - 1)
        return None


class HttpError(RuntimeError):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.http_status = status


def _http_json(url: str, payload: dict[str, Any], headers: dict[str, str], timeout: int = 180) -> dict[str, Any]:
    safe_headers = {key: ("REDACTED" if key.lower() == "authorization" else value) for key, value in headers.items()}
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        body = ""
        try:
            body = error.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            body = ""
        raise HttpError(error.code, redact(f"HTTP {error.code} {body} headers={safe_headers}")) from None
    except urllib.error.URLError as error:
        raise RuntimeError(redact(f"URL error: {error.reason}")) from None


def call_gemini(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, dict[str, Any] | None]:
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model}:generateContent?key={api_key}"
    )
    payload: dict[str, Any] = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": max_tokens,
            "thinkingConfig": {"thinkingBudget": 0},
        },
    }
    try:
        result = _http_json(url, payload, {"Content-Type": "application/json"})
    except HttpError as error:
        if error.http_status == 400 and "thinking" in str(error).lower():
            payload["generationConfig"].pop("thinkingConfig", None)
            result = _http_json(url, payload, {"Content-Type": "application/json"})
        else:
            raise
    parts = []
    for candidate in result.get("candidates") or []:
        for part in (candidate.get("content") or {}).get("parts") or []:
            if part.get("thought"):
                continue
            if part.get("text"):
                parts.append(part["text"])
    return "".join(parts).strip(), result.get("usageMetadata")


def call_nvidia(api_key: str, model: str, prompt: str, max_tokens: int) -> tuple[str, dict[str, Any] | None]:
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": max_tokens,
        "stream": False,
    }
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
    }
    result = _http_json(url, payload, headers)
    choices = result.get("choices") or []
    if not choices:
        return "", result.get("usage")
    message = choices[0].get("message") or {}
    text = (message.get("content") or "").strip()
    return text, result.get("usage")


def chapter_paths() -> list[Path]:
    paths = [CHUNKS_DIR / f"{cid}.md" for cid in CHAPTER_IDS]
    extra = CHUNKS_DIR / "_unassigned.md"
    if extra.is_file():
        paths.append(extra)
    missing = [str(path) for path in paths if not path.is_file() and path.name.startswith("D")]
    if missing:
        raise SystemExit(f"missing chunk files: {missing}; run python scripts/asr_json_to_md.py")
    return paths


def load_manifest_clocks() -> dict[str, str]:
    manifest = json.loads((CHUNKS_DIR / "_manifest.json").read_text(encoding="utf-8"))
    return {row["id"]: row["clock_json"] for row in manifest.get("chapters") or []}


def save_raw(stem: str, suffix: str, text: str) -> None:
    raw_dir = OUT_DIR / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / f"{stem}{suffix}.txt").write_text(text, encoding="utf-8")


def extract_one(client: Stage3bClient, path: Path, skip_existing: bool) -> Path:
    chapter = html_comment(path, "chapter") or path.stem
    clock = html_comment(path, "clock_json") or ""
    dest = INSIGHTS_DIR / f"{path.stem}.md"
    if skip_existing and dest.is_file() and TITLE_RE.search(dest.read_text(encoding="utf-8")):
        return dest
    chunk = path.read_text(encoding="utf-8")
    allowed = utterance_labels(chunk)
    unassigned = path.stem == "_unassigned"
    prompt = extract_prompt(chunk, chapter, unassigned)
    raw = client.complete(prompt, max_tokens=2048, purpose=f"extract:{path.stem}")
    save_raw(path.stem, "_extract", raw)
    title, insights, empty = parse_insights(raw)
    if not title:
        title = "вне глав" if unassigned else "Глава без названия"
    if DISCUSSION_RE.search(title) and not unassigned:
        raw2 = client.complete(
            prompt + "\n\nПовтор: заголовок без слова «обсуждение» / «совещание». "
            "Инсайты оставь; меняй только первую строку `# `.",
            max_tokens=2048,
            purpose=f"extract-retry-title:{path.stem}",
        )
        save_raw(path.stem, "_extract_title_retry", raw2)
        title2, insights2, empty2 = parse_insights(raw2)
        if title2 and not DISCUSSION_RE.search(title2):
            title = title2
            if empty and insights2:
                insights, empty = insights2, empty2
    if not clock:
        clocks = load_manifest_clocks()
        clock = clocks.get(chapter, "")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(render_insight_md(title, chapter, clock, insights, allowed, empty), encoding="utf-8")
    return dest


def concat_insights(paths: list[Path]) -> str:
    parts: list[str] = []
    for path in paths:
        text = path.read_text(encoding="utf-8").strip()
        if path.stem == "_unassigned" and re.search(r"^нет инсайтов\s*$", text, re.M):
            continue
        parts.append(f"===== {path.name} =====\n{text}\n")
    return "\n".join(parts)


def write_run_meta(client: Stage3bClient, extra: dict[str, Any]) -> None:
    payload = {
        "execution_mode": "api",
        "provider": client.provider,
        "model": client.model,
        "gemini_failures": client.gemini_failures,
        "nvidia_failures": client.nvidia_failures,
        "calls": client.calls,
        "error_log": str(ERROR_LOG.relative_to(ROOT)) if ERROR_LOG.is_file() else None,
        **extra,
    }
    (OUT_DIR / "run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def structure_check() -> dict[str, Any]:
    """Deterministic checks: clocks, src labels, report headings. No model."""
    clocks = load_manifest_clocks()
    issues: list[str] = []
    titles: dict[str, str] = {}
    src_ok = 0
    src_bad = 0
    for cid, clock in clocks.items():
        path = INSIGHTS_DIR / f"{cid}.md"
        if not path.is_file():
            issues.append(f"missing insights {cid}")
            continue
        text = path.read_text(encoding="utf-8")
        title_match = TITLE_RE.search(text)
        if not title_match:
            issues.append(f"{cid}: no title")
        else:
            titles[cid] = title_match.group(1).strip()
            if DISCUSSION_RE.search(titles[cid]):
                issues.append(f"{cid}: discussion title")
        got = CLOCK_RE.search(text)
        if not got or got.group(1) != clock:
            issues.append(f"{cid}: clock_json {got.group(1) if got else None} != manifest {clock}")
        chapter = CHAPTER_RE.search(text)
        if chapter and chapter.group(1) != cid:
            issues.append(f"{cid}: chapter comment {chapter.group(1)}")
        allowed = utterance_labels((CHUNKS_DIR / f"{cid}.md").read_text(encoding="utf-8"))
        for src in re.findall(r"^  src:\s*(.+)$", text, re.M):
            if match_src(src, allowed):
                src_ok += 1
            else:
                src_bad += 1
                issues.append(f"{cid}: src not in chunk: {src}")
    report_path = OUT_DIR / "report.md"
    report_clocks: list[str] = []
    if report_path.is_file():
        report = report_path.read_text(encoding="utf-8")
        for heading in ("## Кратко", "## Решения", "## Дальше", "## Открыто", "## По времени"):
            if heading not in report:
                issues.append(f"report missing {heading}")
        report_clocks = re.findall(r"^clock:\s*(\S+)", report, re.M)
        unknown = [item for item in report_clocks if item not in clocks.values()]
        if unknown:
            issues.append(f"report clocks not in manifest: {unknown}")
        for cid in clocks:
            if f"### {cid}" not in report:
                issues.append(f"report missing heading {cid}")
    payload = {
        "ok": not issues,
        "src_ok": src_ok,
        "src_bad": src_bad,
        "titles": titles,
        "report_clocks": report_clocks,
        "issues": issues,
    }
    (OUT_DIR / "structure_check.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def run_api(skip_existing: bool, chapters: list[str] | None, do_assemble: bool, do_check: bool) -> dict[str, Any]:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    INSIGHTS_DIR.mkdir(parents=True, exist_ok=True)
    client = Stage3bClient()
    sources = chapter_paths()
    if chapters:
        wanted = set(chapters)
        sources = [path for path in sources if path.stem in wanted]
        if not sources:
            raise SystemExit(f"no matching chapters: {chapters}")
    insight_paths = [extract_one(client, path, skip_existing) for path in sources]
    all_insights = [INSIGHTS_DIR / f"{cid}.md" for cid in CHAPTER_IDS if (INSIGHTS_DIR / f"{cid}.md").is_file()]
    extra = INSIGHTS_DIR / "_unassigned.md"
    if extra.is_file():
        all_insights.append(extra)
    report_path = OUT_DIR / "report.md"
    if do_assemble:
        bundle = concat_insights(all_insights)
        report = client.complete(assemble_prompt(bundle), max_tokens=4096, purpose="assemble")
        report = strip_model_text(report)
        save_raw("report", "_assemble", report)
        report_path.write_text(report.rstrip() + "\n", encoding="utf-8")
    elif report_path.is_file():
        report = report_path.read_text(encoding="utf-8")
    else:
        report = ""
    hybrid = ROOT / "data" / "3b_data" / "hybrid_asr_gold.md"
    full = ROOT / "data" / "3b_data" / "full_asr.md"
    transcript_path = hybrid if hybrid.is_file() else full
    clocks = list(load_manifest_clocks().values())
    check_path = OUT_DIR / "self_check.md"
    if do_check:
        check_raw = client.complete(
            self_check_prompt(report, transcript_path.read_text(encoding="utf-8"), clocks),
            max_tokens=2048,
            purpose="self_check",
        )
        save_raw("self_check", "", check_raw)
        check_text = strip_model_text(check_raw).rstrip() + "\n"
        if parse_verdict(check_text) is None:
            check_text = check_text.rstrip() + "\nverdict: not_usable\n"
        check_path.write_text(check_text, encoding="utf-8")
    verdict = parse_verdict(check_path.read_text(encoding="utf-8")) if check_path.is_file() else None
    structure = structure_check()
    meta = {
        "input_chunks": [str(path.relative_to(ROOT)) for path in chapter_paths()],
        "insights": [str(path.relative_to(ROOT)) for path in all_insights],
        "report": str(report_path.relative_to(ROOT)),
        "self_check": str(check_path.relative_to(ROOT)) if check_path.is_file() else None,
        "transcript_for_check": str(transcript_path.relative_to(ROOT)),
        "verdict": verdict,
        "structure_ok": structure["ok"],
        "structure_issues": structure["issues"],
    }
    write_run_meta(client, meta)
    return meta


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--chapters", nargs="*", help="only these stems, e.g. D10")
    parser.add_argument("--no-assemble", action="store_true")
    parser.add_argument("--no-self-check", action="store_true")
    parser.add_argument("--structure-only", action="store_true")
    args = parser.parse_args()
    if args.structure_only:
        payload = structure_check()
        print(json.dumps({"structure_ok": payload["ok"], "issues": payload["issues"]}, ensure_ascii=False))
        return
    meta = run_api(
        skip_existing=args.skip_existing,
        chapters=args.chapters,
        do_assemble=not args.no_assemble,
        do_check=not args.no_self_check,
    )
    print(json.dumps({"verdict": meta["verdict"], "structure_ok": meta["structure_ok"], "insights": len(meta["insights"])}))


if __name__ == "__main__":
    main()

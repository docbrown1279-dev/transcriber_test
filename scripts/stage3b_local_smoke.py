#!/usr/bin/env python3
"""Stage 3b local smoke: one D00 extract + assemble of existing Gemini insights.

Does not write insights_d/ or report.md. No API calls.
"""

from __future__ import annotations

import argparse
import json
import resource
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stage3b_insights import (  # noqa: E402
    CHAPTER_IDS,
    CLOCK_RE,
    INSIGHTS_DIR,
    OUT_DIR,
    TITLE_RE,
    assemble_prompt,
    concat_insights,
    extract_prompt,
    html_comment,
    parse_insights,
    render_insight_md,
    strip_model_text,
    utterance_labels,
)

CHUNK_D00 = ROOT / "data" / "3b_data" / "chunks_d" / "D00.md"
LOCAL_D00 = OUT_DIR / "local_d00.md"
LOCAL_REPORT = OUT_DIR / "local_report.md"
LOCAL_SMOKE = OUT_DIR / "local_smoke.md"
GEMINI_D00 = INSIGHTS_DIR / "D00.md"


def peak_rss_mb() -> float:
    # Linux ru_maxrss is kilobytes.
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def load_llm(model: Path, threads: int, n_ctx: int):
    from llama_cpp import Llama

    return Llama(
        model_path=str(model),
        n_ctx=n_ctx,
        n_threads=threads,
        n_threads_batch=threads,
        n_batch=256,
        verbose=False,
    )


def chat(llm, user: str, max_tokens: int) -> tuple[str, float]:
    started = time.monotonic()
    response = llm.create_chat_completion(
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
    raw = (response["choices"][0]["message"]["content"] or "").strip()
    return raw, round(time.monotonic() - started, 3)


def extract_d00(llm) -> dict:
    chunk = CHUNK_D00.read_text(encoding="utf-8")
    clock = html_comment(CHUNK_D00, "clock_json") or ""
    chapter = html_comment(CHUNK_D00, "chapter") or "D00"
    allowed = utterance_labels(chunk)
    prompt = "/no_think\n" + extract_prompt(chunk, chapter, False)
    raw, sec = chat(llm, prompt, max_tokens=2048)
    (OUT_DIR / "raw" / "local_d00.txt").parent.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "raw" / "local_d00.txt").write_text(raw + "\n", encoding="utf-8")
    title, insights, empty = parse_insights(raw)
    parse_ok = bool(title) and (empty or bool(insights))
    if not title:
        title = "Глава без названия"
    LOCAL_D00.write_text(
        render_insight_md(title, chapter, clock, insights, allowed, empty or not insights),
        encoding="utf-8",
    )
    kinds = [row["kind"] for row in insights]
    return {
        "parse_ok": parse_ok,
        "title": title,
        "n_insights": len(insights),
        "kinds": kinds,
        "empty": empty or not insights,
        "runtime_sec": sec,
        "clock_json": clock,
        "clock_copied": bool(CLOCK_RE.search(LOCAL_D00.read_text(encoding="utf-8"))),
    }


def assemble_gemini(llm) -> dict:
    paths = [INSIGHTS_DIR / f"{cid}.md" for cid in CHAPTER_IDS]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit(f"missing Gemini insights (do not rebuild): {missing}")
    bundle = concat_insights(paths)
    prompt = "/no_think\n" + assemble_prompt(bundle)
    raw, sec = chat(llm, prompt, max_tokens=3072)
    (OUT_DIR / "raw" / "local_report.txt").write_text(raw + "\n", encoding="utf-8")
    text = strip_model_text(raw).rstrip() + "\n"
    LOCAL_REPORT.write_text(text, encoding="utf-8")
    headings = [
        name
        for name in ("## Кратко", "## Решения", "## Дальше", "## Открыто", "## По времени")
        for _ in [1]
        if name in text
    ]
    d_heads = [cid for cid in CHAPTER_IDS if f"### {cid}" in text]
    title = TITLE_RE.search(text)
    parse_ok = len(headings) >= 3 or bool(title) or bool(d_heads)
    return {
        "parse_ok": parse_ok,
        "sections": headings,
        "chapter_headings": d_heads,
        "runtime_sec": sec,
        "chars": len(text),
    }


def compare_d00(local: dict) -> list[str]:
    gemini = GEMINI_D00.read_text(encoding="utf-8")
    g_title = TITLE_RE.search(gemini)
    g_title = g_title.group(1).strip() if g_title else ""
    g_kinds = [line.split(":", 1)[1].strip() for line in gemini.splitlines() if line.startswith("- kind:")]
    lines = [
        f"Локальный D00 title: «{local['title']}» ({local['n_insights']} пунктов, kinds={local['kinds'] or '—'}).",
        f"Gemini D00 title: «{g_title}» ({len(g_kinds)} пунктов, kinds={g_kinds}).",
    ]
    if local["empty"]:
        lines.append("Локальный D00: нет инсайтов (парсер пустой или модель отказалась).")
    elif set(local["kinds"]) == set(g_kinds):
        lines.append("Наборы kind совпали с Gemini; формулировки title другие — ожидаемо для 8B.")
    else:
        extra = sorted(set(local["kinds"]) - set(g_kinds))
        missing = sorted(set(g_kinds) - set(local["kinds"]))
        lines.append(
            "Kind расходятся с Gemini"
            + (f"; локально лишние: {extra}" if extra else "")
            + (f"; нет у локального: {missing}" if missing else "")
            + "."
        )
    lines.append("Качество 8B не цель: достаточно, что markdown парсится.")
    return lines


def write_smoke(load_sec: float, extract: dict, assemble: dict, n_ctx: int, model: Path) -> None:
    rss = peak_rss_mb()
    lines = [
        "# Local smoke — Qwen3-8B Q5_K_M",
        "",
        f"- model: `{model.name}`, llama.cpp, n_ctx={n_ctx}, 4 threads, CPU.",
        f"- load_sec: {load_sec}; extract D00: {extract.get('runtime_sec')} s"
        f"{' (reused local_d00.md)' if extract.get('reused') else ''}; "
        f"assemble Gemini insights: {assemble['runtime_sec']} s.",
        f"- peak RSS: {rss} MiB (process).",
        f"- extract parse_ok: {extract['parse_ok']}; assemble parse_ok: {assemble['parse_ok']}; sections={assemble['sections']}; ### глав: {len(assemble['chapter_headings'])}/12.",
        f"- входы: `{CHUNK_D00.relative_to(ROOT)}` → `{LOCAL_D00.relative_to(ROOT)}`; assemble из существующих `insights_d/D00.md`…`D11.md` → `{LOCAL_REPORT.relative_to(ROOT)}`. Gemini файлы не перезаписывались.",
        "",
        "## D00 vs Gemini",
        "",
    ]
    lines.extend(f"- {row}" for row in compare_d00(extract))
    lines.append("")
    LOCAL_SMOKE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_install_fail(message: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOCAL_SMOKE.write_text(
        "# Local smoke — install fail\n\n"
        f"failure_kind: install\n\n{message}\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--n-ctx", type=int, default=16384)
    parser.add_argument("--skip-extract", action="store_true", help="reuse local_d00.md")
    args = parser.parse_args()
    if not args.model.is_file():
        write_install_fail(f"missing GGUF: {args.model}")
        raise SystemExit(2)
    if not CHUNK_D00.is_file():
        raise SystemExit("missing D00 chunk; do not rebuild in this smoke")
    if not GEMINI_D00.is_file():
        raise SystemExit("missing Gemini D00 insights; do not rerun extract")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    last_error = None
    llm = None
    for attempt in range(1, 3):
        try:
            llm = load_llm(args.model, args.threads, args.n_ctx)
            break
        except Exception as exc:
            last_error = exc
            if attempt == 2:
                write_install_fail(f"load failed after 2 tries: {type(exc).__name__}: {exc}")
                raise SystemExit(2) from exc
    assert llm is not None
    load_sec = round(time.monotonic() - started, 3)
    if args.skip_extract and LOCAL_D00.is_file():
        text = LOCAL_D00.read_text(encoding="utf-8")
        title, insights, empty = parse_insights(text)
        extract = {
            "parse_ok": bool(title) and (empty or bool(insights)),
            "title": title,
            "n_insights": len(insights),
            "kinds": [row["kind"] for row in insights],
            "empty": empty or not insights,
            "runtime_sec": None,
            "clock_json": html_comment(LOCAL_D00, "clock_json") or "",
            "clock_copied": True,
            "reused": True,
        }
    else:
        extract = extract_d00(llm)
    assemble = assemble_gemini(llm)
    write_smoke(load_sec, extract, assemble, args.n_ctx, args.model)
    print(
        json.dumps(
            {
                "extract_parse_ok": extract["parse_ok"],
                "assemble_parse_ok": assemble["parse_ok"],
                "load_sec": load_sec,
                "extract_sec": extract["runtime_sec"],
                "assemble_sec": assemble["runtime_sec"],
                "peak_rss_mb": peak_rss_mb(),
            }
        )
    )
    if last_error:
        pass


if __name__ == "__main__":
    main()

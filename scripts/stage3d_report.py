#!/usr/bin/env python3
"""Rewrite 3c insights into report.md with speaker slots and timed key points. Does not touch insights.md."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from stage3c_run import ApiClient, LocalClient, strip_model_text  # noqa: E402

TRANSCRIPT = ROOT / "data" / "3c_data" / "transcript.md"
OUT = ROOT / "results" / "llm" / "3c"
INSIGHTS = {
    "gemini": OUT / "gemini" / "insights.md",
    "local": OUT / "local" / "insights.md",
}
SPEAKER_RE = re.compile(r"SPEAKER_[A-Z0-9]+")
SRC_RE = re.compile(
    r"src:\s*\[(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2}) \| (SPEAKER_[A-Z0-9]+)"
)
KEY_CLOCK_RE = re.compile(
    r"\((SPEAKER_[A-Z0-9]+);\s*(\d{2}:\d{2}:\d{2}\.\d{2})[–-](\d{2}:\d{2}:\d{2}\.\d{2})\)"
)
def speakers_in(text: str) -> list[str]:
    return sorted(set(SPEAKER_RE.findall(text)), key=lambda name: (len(name), name))


def src_triples(insights: str) -> set[tuple[str, str, str]]:
    return {(a, b, spk) for a, b, spk in SRC_RE.findall(insights)}


def report_prompt(insights: str, speakers: list[str]) -> str:
    roster = "\n".join(f"- {name} →" for name in speakers)
    dummy = "- согласовать смету до пятницы (SPEAKER_02; 00:12:04.00–00:12:18.50)"
    return (
        "Собери отчёт секретаря из готовых инсайтов. Не добавляй факты, числа и людей, которых нет во входе.\n"
        "Имена и должности не выдумывай: в блоке «Спикеры» оставь пустое место после стрелки.\n"
        "Идентификаторы копируй как есть (SPEAKER_02 и SPEAKER_B — разные слоты, не сливай).\n"
        "Каждый пункт «Ключевые инсайты» обязан кончаться скобкой с id и часами из строки src инсайта.\n"
        f"Формат скобки как здесь (это ФОРМА, не факт этой записи): {dummy}\n"
        "Если у тезиса нет src — не ставь его в «Ключевые». Время не выдумывай.\n"
        "Главы D00…D11 сохрани все, даже с «нет инсайтов».\n\n"
        "Формат, без вступления:\n"
        "# Отчёт\n"
        "## Спикеры\n"
        f"{roster}\n"
        "## Оценка\n"
        "(2–5 предложений)\n"
        "## Ключевые инсайты\n"
        "- тезис (SPEAKER_xx; HH:MM:SS.cc–HH:MM:SS.cc)\n"
        "## По главам\n"
        "### D00 — <title>\n"
        "clock: <как во входе>\n"
        "- тезис\n"
        "  кто: SPEAKER_xx\n"
        "  когда: HH:MM:SS.cc–HH:MM:SS.cc\n\n"
        f"СПИСОК ID (все вывести в «Спикеры»):\n{roster}\n\n"
        f"ИНСАЙТЫ:\n{insights}\n"
    )


def check_report(path: Path, insights_path: Path) -> dict[str, Any]:
    report = path.read_text(encoding="utf-8")
    insights = insights_path.read_text(encoding="utf-8")
    transcript = TRANSCRIPT.read_text(encoding="utf-8")
    needed = set(speakers_in(transcript))
    listed = set(speakers_in("\n".join(line for line in report.splitlines() if "→" in line or "->" in line)))
    if not listed:
        listed = set(speakers_in(report.split("## Оценка")[0] if "## Оценка" in report else report[:800]))
    allowed = src_triples(insights)
    issues: list[str] = []
    missing = sorted(needed - listed)
    extra = sorted(listed - needed)
    if missing:
        issues.append(f"speakers missing {missing}")
    if extra:
        issues.append(f"speakers extra {extra}")
    if "## Спикеры" not in report or "## Ключевые инсайты" not in report:
        issues.append("missing sections")
    for tag in [f"D{i:02d}" for i in range(12)]:
        if f"### {tag} — " not in report:
            issues.append(f"missing {tag}")
    key_block = report.split("## Ключевые инсайты", 1)[-1].split("## По главам", 1)[0]
    timed = 0
    untimed = 0
    bad_clock = 0
    for line in key_block.splitlines():
        if not line.startswith("- "):
            continue
        match = KEY_CLOCK_RE.search(line)
        if not match:
            untimed += 1
            issues.append(f"key insight without clock: {line[:80]}")
            continue
        timed += 1
        triple = (match.group(2), match.group(3), match.group(1))
        if triple not in allowed:
            bad_clock += 1
            issues.append(f"clock not in 3c src: {match.group(0)}")
    payload = {
        "ok": not issues,
        "file": str(path.relative_to(ROOT)),
        "speakers_listed": len(listed),
        "speakers_needed": len(needed),
        "key_timed": timed,
        "key_untimed": untimed,
        "key_clock_unknown": bad_clock,
        "issues": issues,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def run_provider(name: str, client: Any) -> None:
    insights_path = INSIGHTS[name]
    if not insights_path.is_file():
        raise SystemExit(f"missing {insights_path}; run Stage 3c first")
    insights = insights_path.read_text(encoding="utf-8")
    speakers = speakers_in(TRANSCRIPT.read_text(encoding="utf-8"))
    dest = OUT / name
    dest.mkdir(parents=True, exist_ok=True)
    raw = client.complete(report_prompt(insights, speakers), max_tokens=4096, purpose="report")
    (dest / "raw").mkdir(exist_ok=True)
    (dest / "raw" / "report.txt").write_text(raw, encoding="utf-8")
    text = strip_model_text(raw)
    if not text.lstrip().startswith("#"):
        text = "# Отчёт\n\n" + text
    (dest / "report.md").write_text(text.rstrip() + "\n", encoding="utf-8")
    meta = {
        "provider": getattr(client, "provider", name),
        "model": getattr(client, "model", name),
        "calls": getattr(client, "calls", []),
        "source_insights": str(insights_path.relative_to(ROOT)),
        "speakers": speakers,
    }
    if hasattr(client, "load_sec"):
        meta["load_sec"] = client.load_sec
    (dest / "run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"folder": name, "speakers": speakers, "model": meta["model"]}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--provider", choices=("gemini", "local", "both"), default="gemini")
    parser.add_argument("--model", type=Path, default=ROOT / "models" / "Qwen3-8B-Q5_K_M.gguf")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--n-ctx", type=int, default=8192)
    parser.add_argument("--check", type=Path, help="regex-check a 3d report.md")
    args = parser.parse_args()
    if args.check:
        folder = "local" if "local" in str(args.check) else "gemini"
        payload = check_report(args.check, INSIGHTS[folder])
        raise SystemExit(0 if payload["ok"] else 1)
    if not TRANSCRIPT.is_file():
        raise SystemExit("missing data/3c_data/transcript.md")
    OUT.mkdir(parents=True, exist_ok=True)
    if args.provider in ("gemini", "both"):
        run_provider("gemini", ApiClient(OUT / "gemini" / "api_errors_report.jsonl"))
    if args.provider in ("local", "both"):
        if not args.model.is_file():
            dest = OUT / "local"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "report.md").write_text(
                f"# Отчёт\n\nfailure_kind: install\n\nmissing GGUF: {args.model}\n",
                encoding="utf-8",
            )
            raise SystemExit(2)
        local = None
        last_error: Exception | None = None
        for _ in range(2):
            try:
                local = LocalClient(args.model, args.threads, args.n_ctx)
                break
            except Exception as exc:
                last_error = exc
        if local is None:
            dest = OUT / "local"
            dest.mkdir(parents=True, exist_ok=True)
            (dest / "report.md").write_text(
                f"# Отчёт\n\nfailure_kind: install\n\n{type(last_error).__name__}: {last_error}\n",
                encoding="utf-8",
            )
            raise SystemExit(2)
        run_provider("local", local)


if __name__ == "__main__":
    main()

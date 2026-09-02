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
BRACKET_CLOCK_RE = re.compile(r"\[(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2})\]")


def speakers_in(text: str) -> list[str]:
    return sorted(set(SPEAKER_RE.findall(text)), key=lambda name: (len(name), name))


def src_triples(insights: str) -> set[tuple[str, str, str]]:
    return {(a, b, spk) for a, b, spk in SRC_RE.findall(insights)}


def insight_rows(insights: str) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    pending: str | None = None
    for line in insights.splitlines():
        stripped = line.strip()
        if stripped.startswith("- "):
            pending = stripped[2:].strip()
            continue
        match = SRC_RE.search(stripped)
        if match and pending:
            rows.append((pending, match.group(1), match.group(2), match.group(3)))
            pending = None
    return rows


def inject_speakers(text: str, speakers: list[str]) -> str:
    roster = "## Спикеры\n" + "\n".join(f"- {name} →" for name in speakers) + "\n"
    if re.search(r"^##\s*Спикеры\s*$", text, re.M):
        return re.sub(
            r"^##\s*Спикеры\s*\n(?:.*\n)*?(?=^## |\Z)",
            roster + "\n",
            text,
            count=1,
            flags=re.M,
        )
    if text.lstrip().startswith("#"):
        first, _, rest = text.lstrip().partition("\n")
        return first + "\n\n" + roster + "\n" + rest.lstrip()
    return roster + "\n" + text


def _best_row(thesis: str, rows: list[tuple[str, str, str, str]]) -> tuple[str, str, str] | None:
    needle = set(re.findall(r"[А-Яа-яA-Za-z0-9]{4,}", thesis.lower()))
    best: tuple[int, tuple[str, str, str]] | None = None
    for text, start, end, speaker in rows:
        hay = set(re.findall(r"[А-Яа-яA-Za-z0-9]{4,}", text.lower()))
        score = len(needle & hay)
        if score and (best is None or score > best[0]):
            best = (score, (start, end, speaker))
    return best[1] if best and best[0] >= 2 else None


def attach_key_refs(text: str, insights: str) -> str:
    rows = insight_rows(insights)
    allowed = {(start, end, speaker) for _thesis, start, end, speaker in rows}
    if "## Ключевые инсайты" not in text:
        return text
    head, rest = text.split("## Ключевые инсайты", 1)
    if "## По главам" in rest:
        keys, tail = rest.split("## По главам", 1)
        tail = "## По главам" + tail
    else:
        keys, tail = rest, ""
    out: list[str] = []
    for line in keys.splitlines():
        if not line.startswith("- "):
            out.append(line)
            continue
        match = KEY_CLOCK_RE.search(line)
        if match and (match.group(2), match.group(3), match.group(1)) in allowed:
            out.append(line)
            continue
        thesis = KEY_CLOCK_RE.sub("", line[2:]).strip()
        thesis = BRACKET_CLOCK_RE.sub("", thesis).strip()
        picked = None
        bracket = BRACKET_CLOCK_RE.search(line)
        if bracket:
            for start, end, speaker in allowed:
                if start == bracket.group(1) and end == bracket.group(2):
                    picked = (start, end, speaker)
                    break
        if picked is None:
            picked = _best_row(thesis, rows)
        if picked:
            start, end, speaker = picked
            out.append(f"- {thesis} ({speaker}; {start}–{end})")
        # drop bullets that cannot be grounded to a 3c src
    return head + "## Ключевые инсайты" + "\n".join(out) + "\n" + tail


HEAD_RE = re.compile(r"^### (D\d{2}) — (.+)$")
CLOCK_LINE_RE = re.compile(r"^clock: (.+)$")


def render_chapters(insights: str) -> str:
    lines = ["## По главам", ""]
    title = clock = None
    pending: str | None = None
    for raw in insights.splitlines():
        line = raw.strip()
        head = HEAD_RE.match(line)
        if head:
            title = f"### {head.group(1)} — {head.group(2)}"
            clock = None
            pending = None
            continue
        clock_match = CLOCK_LINE_RE.match(line)
        if clock_match and title:
            lines.append(title)
            lines.append(f"clock: {clock_match.group(1)}")
            continue
        if line.lower() == "нет инсайтов":
            lines.append("нет инсайтов")
            lines.append("")
            continue
        if line.startswith("- "):
            pending = line[2:].strip()
            continue
        src = SRC_RE.search(line)
        if src and pending:
            lines.append(f"- {pending}")
            lines.append(f"  кто: {src.group(3)}")
            lines.append(f"  когда: {src.group(1)}–{src.group(2)}")
            pending = None
            continue
    if not lines[-1]:
        lines.pop()
    return "\n".join(lines).rstrip() + "\n"


def ensure_chapters(text: str, insights: str) -> str:
    block = render_chapters(insights)
    if re.search(r"^##\s*По главам\s*$", text, re.M):
        return re.sub(r"^##\s*По главам\s*\n[\s\S]*\Z", block, text, count=1, flags=re.M)
    return text.rstrip() + "\n\n" + block


def strip_chapters(text: str) -> str:
    """Chapter list lives in insights.md; do not keep a dump in the meeting report."""
    cleaned = re.sub(r"^##\s*По главам\s*\n[\s\S]*\Z", "", text, flags=re.M)
    cleaned = re.sub(r"^### D\d{2} — .+\n(?:clock: .+\n)?(?:.*\n)*?(?=^### D\d{2} — |\Z)", "", cleaned, flags=re.M)
    return cleaned.rstrip() + "\n"


def report_prompt(insights: str, speakers: list[str]) -> str:
    roster = "\n".join(f"- {name} →" for name in speakers)
    dummy = "- канализация идёт через паркинг, потому что так заданы точки в ТУ (SPEAKER_B; 00:00:22.30–00:01:04.30)"
    return (
        "Собери КОРОТКИЙ отчёт секретаря из готовых инсайтов. Не добавляй факты, числа и людей, которых нет во входе.\n"
        "Имена и должности не выдумывай: в блоке «Спикеры» оставь пустое место после стрелки.\n"
        "Идентификаторы копируй как есть (SPEAKER_02 и SPEAKER_B — разные слоты, не сливай).\n\n"
        "В «Ключевые инсайты» ставь пункт ТОЛЬКО если верно одно:\n"
        "1) одна тема звучит минимум в трёх разных репликах (не три пересказа одной фразы);\n"
        "2) явный вопрос одного спикера и ответ другого; мелкий диалог («Андрей подойдёт?» — «да») не считается;\n"
        "3) один спикер раскрывает проблему: что сделать и почему важно, либо что не сделали и почему.\n"
        "Не бери: реплику без развития, приветствия, переспрашивания, общие «направим»/«уточним» без объекта.\n"
        "Не копируй все пункты глав. 5–12 ключевых тезисов на всю встречу достаточно. Полный разбор по D00…D11 уже есть отдельно — блок «По главам» НЕ пиши.\n\n"
        "Каждый пункт «Ключевые инсайты» кончается скобкой с id и часами из строки src.\n"
        f"Формат скобки (это ФОРМА, не факт этой записи): {dummy}\n"
        "Если у тезиса нет src — не ставь его. Время не выдумывай.\n\n"
        "Формат, без вступления:\n"
        "# Отчёт\n"
        "## Спикеры\n"
        f"{roster}\n"
        "## Оценка\n"
        "(2–5 предложений: характер встречи, шум ASR, были ли решения)\n"
        "## Ключевые инсайты\n"
        "- тезис (SPEAKER_xx; HH:MM:SS.cc–HH:MM:SS.cc)\n\n"
        "Не добавляй секции «По главам», «По времени», «Решения».\n\n"
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
    if re.search(r"^##\s*По главам\s*$", report, re.M) or re.search(r"^### D\d{2} — ", report, re.M):
        issues.append("chapter dump present; belongs in insights.md")
    n_src = len(insight_rows(insights))
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
    if timed == 0:
        issues.append("no key insights")
    if n_src >= 15 and timed >= min(n_src - 2, 20):
        issues.append(f"key dump {timed}/{n_src}; keep 5–12 meeting-level items")
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
    raw = client.complete(report_prompt(insights, speakers), max_tokens=2048, purpose="report")
    (dest / "raw").mkdir(exist_ok=True)
    (dest / "raw" / "report.txt").write_text(raw, encoding="utf-8")
    text = strip_model_text(raw)
    if not text.lstrip().startswith("#"):
        text = "# Отчёт\n\n" + text
    text = inject_speakers(text, speakers)
    text = attach_key_refs(text, insights)
    text = strip_chapters(text)
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
    (dest / "report_run.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
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
        check_path = args.check if args.check.is_absolute() else ROOT / args.check
        folder = "local" if "local" in str(check_path) else "gemini"
        payload = check_report(check_path, INSIGHTS[folder])
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

#!/usr/bin/env python3
"""Stage 3c sources: one transcript + D chapter clocks. No C, no 12 chunk files.

Transcript is GigaAM with gold spliced into the four eval windows (same as 3b hybrid).
Cloud agents use the committed files; do not read eval/.

  python scripts/stage3c_pack.py          # write data/3c_data/{transcript.md,chapters.json}
  python scripts/stage3c_pack.py --slice  # also write _slices/D00.md … D11.md (gitignored)
  python scripts/stage3c_pack.py --check results/llm/3c/gemini/insights.md
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from asr_json_to_md import (  # noqa: E402
    CHAPTERS,
    CLIPS,
    FULL_ASR,
    format_line,
    fmt_ts,
    load_chapters,
    load_json,
    overlaps,
    parse_md_utterances,
    parse_ts,
    segments_from,
    shift,
)

OUT = ROOT / "data" / "3c_data"
TRANSCRIPT = OUT / "transcript.md"
CHAPTERS_JSON = OUT / "chapters.json"
SLICES = OUT / "_slices"
SRC_RE = re.compile(
    r"src:\s*\[(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2}) \| ([A-Z0-9_]+)(?: \| D\d{2})?\]"
)
HEAD_RE = re.compile(r"^### (D\d{2}) — (.+)$", re.M)
CLOCK_RE = re.compile(r"^clock: (\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2})$", re.M)


def gold_windows() -> list[dict]:
    rows = []
    for clip_id, offset, duration in CLIPS:
        start, end = float(offset), float(offset) + float(duration)
        rows.append(
            {
                "id": clip_id,
                "clock": f"{fmt_ts(start)}-{fmt_ts(end)}",
                "start_sec": start,
                "end_sec": end,
            }
        )
    return rows


def find_hybrid() -> Path | None:
    for path in (
        ROOT / ".trash" / "3b_data" / "hybrid_asr_gold.md",
        ROOT / "data" / "3b_data" / "hybrid_asr_gold.md",
    ):
        if path.is_file():
            return path
    return None


def load_gold_from_eval() -> tuple[list[dict], list[tuple[float, float]]] | None:
    eval_dir = ROOT / "eval"
    if not eval_dir.is_dir():
        return None
    gold_rows: list[dict] = []
    windows: list[tuple[float, float]] = []
    for clip_id, offset, duration in CLIPS:
        path = eval_dir / f"{clip_id}.json"
        if not path.is_file():
            continue
        windows.append((float(offset), float(offset) + float(duration)))
        gold_rows.extend(shift(segments_from(load_json(path)), float(offset)))
    if not gold_rows:
        return None
    return gold_rows, windows


def splice(asr_rows: list[dict], gold_rows: list[dict], windows: list[tuple[float, float]]) -> list[dict]:
    kept = [row for row in asr_rows if not overlaps(row["start"], row["end"], windows)]
    return sorted(kept + gold_rows, key=lambda row: (row["start"], row["end"]))


def load_asr_rows() -> list[dict]:
    if FULL_ASR.is_file():
        return segments_from(load_json(FULL_ASR))
    for path in (
        ROOT / ".trash" / "3b_data" / "full_asr.md",
        ROOT / "data" / "3b_data" / "full_asr.md",
    ):
        if path.is_file():
            return parse_md_utterances(path)
    return []


def load_utterances() -> tuple[list[dict], str]:
    hybrid = find_hybrid()
    if hybrid is not None:
        return parse_md_utterances(hybrid), f"hybrid:{hybrid.name}"
    asr_rows = load_asr_rows()
    gold = load_gold_from_eval()
    if asr_rows and gold:
        gold_rows, windows = gold
        return splice(asr_rows, gold_rows, windows), "hybrid:eval"
    if TRANSCRIPT.is_file():
        return parse_md_utterances(TRANSCRIPT), "transcript.md"
    if asr_rows:
        return asr_rows, "asr-only"
    raise SystemExit("no hybrid, no eval gold, no ASR JSON, no transcript.md")


def chapter_rows() -> list[dict]:
    rows = []
    for chapter in load_chapters("D"):
        tag = f"D{chapter['id']:02d}"
        rows.append(
            {
                "id": tag,
                "clock": f"{fmt_ts(chapter['start'])}-{fmt_ts(chapter['end'])}",
                "start_sec": chapter["start"],
                "end_sec": chapter["end"],
            }
        )
    if not rows:
        raise SystemExit(f"missing {CHAPTERS['D']}")
    return rows


def write_transcript(utterances: list[dict], source: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    windows = "; ".join(row["clock"] for row in gold_windows())
    lines = [
        f"<!-- source: {source} -->",
        "<!-- line: [HH:MM:SS.cc-HH:MM:SS.cc | SPEAKER] text -->",
        "<!-- clocks of chapters D: chapters.json, not this file -->",
        f"<!-- gold_windows: {windows} -->",
        "<!-- gold replaces ASR inside those 4 eval clips; the rest is GigaAM -->",
        "",
    ]
    for row in utterances:
        lines.append(format_line(row["start"], row["end"], row["speaker"], row["text"]))
    TRANSCRIPT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_chapters(rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    CHAPTERS_JSON.write_text(
        json.dumps(
            {
                "letter": "D",
                "chapters_json": str(CHAPTERS["D"].relative_to(ROOT)),
                "transcript": str(TRANSCRIPT.relative_to(ROOT)),
                "gold_windows": gold_windows(),
                "chapters": rows,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def overlap(start: float, end: float, chapter: dict) -> bool:
    return start < float(chapter["end_sec"]) and end > float(chapter["start_sec"])


def slice_chapter(utterances: list[dict], chapter: dict) -> str:
    body = [
        f"<!-- chapter: {chapter['id']} -->",
        f"<!-- clock: {chapter['clock']} -->",
        "",
    ]
    for row in utterances:
        if overlap(row["start"], row["end"], chapter):
            body.append(format_line(row["start"], row["end"], row["speaker"], row["text"]))
    body.append("")
    return "\n".join(body)


def write_slices(utterances: list[dict], chapters: list[dict]) -> None:
    SLICES.mkdir(parents=True, exist_ok=True)
    for chapter in chapters:
        (SLICES / f"{chapter['id']}.md").write_text(
            slice_chapter(utterances, chapter), encoding="utf-8"
        )


def check_insights(path: Path, chapters: list[dict]) -> dict:
    text = path.read_text(encoding="utf-8")
    by_id = {row["id"]: row for row in chapters}
    heads = HEAD_RE.findall(text)
    clocks = CLOCK_RE.findall(text)
    issues: list[str] = []
    if len(heads) != len(clocks):
        issues.append(f"heads {len(heads)} vs clocks {len(clocks)}")
    missing = sorted(set(by_id) - {tag for tag, _ in heads})
    extra = sorted({tag for tag, _ in heads} - set(by_id))
    if missing:
        issues.append(f"missing {missing}")
    if extra:
        issues.append(f"extra {extra}")
    mismatch = 0
    for (tag, _title), (a, b) in zip(heads, clocks):
        got = f"{a}-{b}"
        exp = by_id.get(tag, {}).get("clock")
        if exp != got:
            mismatch += 1
            issues.append(f"{tag} {got} != {exp}")
    src_ok = src_bad = 0
    current: dict | None = None
    for line in text.splitlines():
        head = re.match(r"^### (D\d{2}) — ", line)
        if head:
            current = by_id.get(head.group(1))
            continue
        match = SRC_RE.search(line)
        if not match or not current:
            continue
        start, end = parse_ts(match.group(1)), parse_ts(match.group(2))
        if overlap(start, end, current):
            src_ok += 1
        else:
            src_bad += 1
            issues.append(f"{current['id']}: src outside {match.group(1)}-{match.group(2)}")
    payload = {
        "ok": not issues,
        "file": str(path.relative_to(ROOT)),
        "n_sections": len(heads),
        "clock_mismatch": mismatch,
        "src_ok": src_ok,
        "src_bad": src_bad,
        "issues": issues,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slice", action="store_true", help="write gitignored _slices/D*.md")
    parser.add_argument("--check", type=Path, help="regex-check an insights.md")
    args = parser.parse_args()
    if args.check:
        chapters = json.loads(CHAPTERS_JSON.read_text(encoding="utf-8"))["chapters"]
        payload = check_insights(args.check, chapters)
        raise SystemExit(0 if payload["ok"] else 1)
    utterances, source = load_utterances()
    chapters = chapter_rows()
    write_transcript(utterances, source)
    write_chapters(chapters)
    if args.slice:
        write_slices(utterances, chapters)
    print(
        json.dumps(
            {
                "transcript": str(TRANSCRIPT.relative_to(ROOT)),
                "chapters": str(CHAPTERS_JSON.relative_to(ROOT)),
                "source": source,
                "n_lines": len(utterances),
                "n_chapters": len(chapters),
                "gold_windows": [row["clock"] for row in gold_windows()],
                "slices": str(SLICES.relative_to(ROOT)) if args.slice else None,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

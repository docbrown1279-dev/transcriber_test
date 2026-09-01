#!/usr/bin/env python3
"""Stage 3c sources: one transcript + D chapter clocks. No gold, no C, no 12 chunk files.

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
    FULL_ASR,
    format_line,
    fmt_ts,
    load_chapters,
    load_json,
    parse_md_utterances,
    parse_ts,
    segments_from,
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


def load_utterances() -> list[dict]:
    if FULL_ASR.is_file():
        return segments_from(load_json(FULL_ASR))
    legacy = ROOT / "data" / "3b_data" / "full_asr.md"
    trash = ROOT / ".trash" / "3b_data" / "full_asr.md"
    for path in (TRANSCRIPT, legacy, trash):
        if path.is_file():
            return parse_md_utterances(path)
    raise SystemExit("no ASR JSON and no transcript.md — cannot pack 3c sources")


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


def write_transcript(utterances: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines = [
        "<!-- source: results/asr/2/gigaam_v3_rnnt/meeting_sample.json -->",
        "<!-- line: [HH:MM:SS.cc-HH:MM:SS.cc | SPEAKER] text -->",
        "<!-- clocks of chapters D: chapters.json, not this file -->",
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
    utterances = load_utterances()
    chapters = chapter_rows()
    write_transcript(utterances)
    write_chapters(chapters)
    if args.slice:
        write_slices(utterances, chapters)
    print(
        json.dumps(
            {
                "transcript": str(TRANSCRIPT.relative_to(ROOT)),
                "chapters": str(CHAPTERS_JSON.relative_to(ROOT)),
                "n_lines": len(utterances),
                "n_chapters": len(chapters),
                "slices": str(SLICES.relative_to(ROOT)) if args.slice else None,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

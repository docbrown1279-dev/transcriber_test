#!/usr/bin/env python3
"""ASR / gold JSON → markdown lines that regex can split.

Line shape (one utterance):
  [HH:MM:SS.cc-HH:MM:SS.cc | SPEAKER | D00] text

Skipped: id, gain, rms, volume. Clock is always the full meeting unless noted.
Gold is read only if --gold and eval/ exists (local machine). Cloud agents skip it.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "3b_data"
FULL_ASR = ROOT / "results" / "asr" / "2" / "gigaam_v3_rnnt" / "meeting_sample.json"
CLIP_ASR_DIR = ROOT / "results" / "asr" / "1f" / "pyannote31"
CHAPTERS = {
    "D": ROOT / "results" / "chunking" / "2b" / "exp_d_chapters.json",
    "C": ROOT / "results" / "chunking" / "2b" / "exp_c_chapters.json",
}
CLIPS = [
    ("test_voice", 0.0, 83.0),
    ("test_apartments", 570.0, 85.0),
    ("test_transformers", 875.0, 85.0),
    ("test_ninth", 1245.0, 85.0),
]
LINE_RE = re.compile(
    r"^\[(\d{2}:\d{2}:\d{2}\.\d{2})-(\d{2}:\d{2}:\d{2}\.\d{2}) \| ([A-Z0-9_]+)(?: \| ([CD]\d{2}))?\] (.*)$"
)


def fmt_ts(sec: float) -> str:
    sec = max(0.0, float(sec))
    hours = int(sec // 3600)
    minutes = int((sec % 3600) // 60)
    seconds = sec % 60
    return f"{hours:02d}:{minutes:02d}:{seconds:05.2f}"


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def segments_from(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("segments") or []
    out: list[dict[str, Any]] = []
    for row in rows:
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        out.append(
            {
                "start": float(row["start"]),
                "end": float(row["end"]),
                "speaker": str(row.get("speaker") or "UNK"),
                "text": text,
            }
        )
    return out


def load_chapters(letter: str) -> list[dict[str, Any]]:
    path = CHAPTERS[letter]
    if not path.is_file():
        return []
    rows = load_json(path).get("chapters") or []
    return [
        {
            "id": int(row["id"]),
            "start": float(row["start"]),
            "end": float(row["end"]),
        }
        for row in rows
    ]


def chapter_tag(start: float, chapters: list[dict[str, Any]], letter: str) -> str | None:
    for row in chapters:
        if row["start"] - 1e-6 <= start < row["end"] + 1e-6:
            return f"{letter}{row['id']:02d}"
    return None


def format_line(
    start: float,
    end: float,
    speaker: str,
    text: str,
    chapter: str | None = None,
) -> str:
    label = f"[{fmt_ts(start)}-{fmt_ts(end)} | {speaker}"
    if chapter:
        label += f" | {chapter}"
    label += "]"
    text = " ".join(text.split())
    return f"{label} {text}"


def header(source: str, clock: str, extra: str = "") -> str:
    lines = [
        f"<!-- source: {source} -->",
        f"<!-- clock: {clock} -->",
        "<!-- line: [HH:MM:SS.cc-HH:MM:SS.cc | SPEAKER | CHAPTER?] text -->",
        "<!-- skip: id, gain, rms, volume -->",
    ]
    if extra:
        lines.append(f"<!-- {extra} -->")
    lines.append("")
    return "\n".join(lines)


def write_utterances(
    dest: Path,
    source: str,
    clock: str,
    rows: list[dict[str, Any]],
    chapters: list[dict[str, Any]] | None = None,
    letter: str | None = None,
    extra: str = "",
) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    body: list[str] = [header(source, clock, extra)]
    current_chapter: str | None = None
    for row in rows:
        tag = None
        if chapters and letter:
            tag = chapter_tag(row["start"], chapters, letter)
            if tag != current_chapter:
                current_chapter = tag
                if tag:
                    body.append(f"\n## {tag}\n")
        body.append(format_line(row["start"], row["end"], row["speaker"], row["text"], tag))
    dest.write_text("\n".join(body) + "\n", encoding="utf-8")


def shift(rows: list[dict[str, Any]], offset: float) -> list[dict[str, Any]]:
    return [
        {
            "start": row["start"] + offset,
            "end": row["end"] + offset,
            "speaker": row["speaker"],
            "text": row["text"],
        }
        for row in rows
    ]


def overlaps(start: float, end: float, windows: list[tuple[float, float]]) -> bool:
    for left, right in windows:
        if start < right and end > left:
            return True
    return False


def parse_ts(label: str) -> float:
    hours, minutes, seconds = label.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_md_utterances(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = LINE_RE.match(line)
        if not match:
            continue
        rows.append(
            {
                "start": parse_ts(match.group(1)),
                "end": parse_ts(match.group(2)),
                "speaker": match.group(3),
                "text": match.group(5),
            }
        )
    return rows


def write_chunk_dir(letter: str, source_md: Path) -> None:
    chapters = load_chapters(letter)
    utterances = parse_md_utterances(source_md)
    dest = OUT / f"chunks_{letter.lower()}"
    dest.mkdir(parents=True, exist_ok=True)
    assigned = [False] * len(utterances)
    manifest: list[dict[str, Any]] = []
    for chapter in chapters:
        tag = f"{letter}{chapter['id']:02d}"
        clock = f"{fmt_ts(chapter['start'])}-{fmt_ts(chapter['end'])}"
        lines: list[str] = [
            f"<!-- chapter: {tag} -->",
            f"<!-- clock_json: {clock} -->",
            f"<!-- start_sec: {chapter['start']} -->",
            f"<!-- end_sec: {chapter['end']} -->",
            f"<!-- source: {source_md.name} -->",
            "<!-- title is written by the LLM in the insights file, not here -->",
            "",
        ]
        n = 0
        for index, row in enumerate(utterances):
            if row["start"] < chapter["end"] and row["end"] > chapter["start"]:
                assigned[index] = True
                lines.append(
                    format_line(row["start"], row["end"], row["speaker"], row["text"], tag)
                )
                n += 1
        (dest / f"{tag}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        manifest.append(
            {
                "id": tag,
                "start_sec": chapter["start"],
                "end_sec": chapter["end"],
                "clock_json": clock,
                "n_lines": n,
                "input": str((dest / f"{tag}.md").relative_to(ROOT)),
            }
        )
    leftover = [row for flag, row in zip(assigned, utterances) if not flag]
    if leftover:
        gap_lines = [
            f"<!-- chapter: {letter}_unassigned -->",
            f"<!-- source: {source_md.name} -->",
            "<!-- lines outside 2b chapter intervals -->",
            "",
        ]
        for row in leftover:
            gap_lines.append(format_line(row["start"], row["end"], row["speaker"], row["text"]))
        (dest / "_unassigned.md").write_text("\n".join(gap_lines) + "\n", encoding="utf-8")
    (dest / "_manifest.json").write_text(
        json.dumps(
            {
                "letter": letter,
                "source": str(source_md.relative_to(ROOT)),
                "chapters_json": str(CHAPTERS[letter].relative_to(ROOT)),
                "chapters": manifest,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def write_full_asr() -> list[dict[str, Any]]:
    payload = load_json(FULL_ASR)
    rows = segments_from(payload)
    write_utterances(OUT / "full_asr.md", str(FULL_ASR.relative_to(ROOT)), "meeting", rows)
    chapters = load_chapters("D")
    write_utterances(
        OUT / "full_asr_d.md",
        str(FULL_ASR.relative_to(ROOT)),
        "meeting",
        rows,
        chapters=chapters,
        letter="D",
        extra=f"chapter tags from {CHAPTERS['D'].relative_to(ROOT)}",
    )
    return rows


def write_clips_asr() -> None:
    blocks: list[str] = [
        header("results/asr/1f/pyannote31", "meeting = clip + offset", "four eval clips, GigaAM on pyannote 3.1")
    ]
    for clip_id, offset, _duration in CLIPS:
        path = CLIP_ASR_DIR / f"{clip_id}.json"
        if not path.is_file():
            continue
        blocks.append(f"\n# {clip_id}  offset={offset:.1f}s\n")
        for row in shift(segments_from(load_json(path)), offset):
            blocks.append(format_line(row["start"], row["end"], row["speaker"], row["text"]))
    (OUT / "clips_asr.md").write_text("\n".join(blocks) + "\n", encoding="utf-8")


def try_gold() -> tuple[list[dict[str, Any]], list[tuple[float, float]]] | None:
    eval_dir = ROOT / "eval"
    if not eval_dir.is_dir():
        return None
    gold_rows: list[dict[str, Any]] = []
    windows: list[tuple[float, float]] = []
    blocks: list[str] = [
        header(
            "eval/test_*.json",
            "meeting = clip + offset",
            "human gold, 4 disjoint clips — not a full meeting",
        )
    ]
    for clip_id, offset, duration in CLIPS:
        path = eval_dir / f"{clip_id}.json"
        if not path.is_file():
            continue
        windows.append((offset, offset + duration))
        blocks.append(f"\n# {clip_id}  offset={offset:.1f}s\n")
        for row in shift(segments_from(load_json(path)), offset):
            gold_rows.append(row)
            blocks.append(format_line(row["start"], row["end"], row["speaker"], row["text"]))
    if not gold_rows:
        return None
    (OUT / "clips_gold.md").write_text("\n".join(blocks) + "\n", encoding="utf-8")
    return gold_rows, windows


def write_hybrid(asr_rows: list[dict[str, Any]], gold_rows: list[dict[str, Any]], windows: list[tuple[float, float]]) -> None:
    kept = [row for row in asr_rows if not overlaps(row["start"], row["end"], windows)]
    merged = sorted(kept + gold_rows, key=lambda row: (row["start"], row["end"]))
    write_utterances(
        OUT / "hybrid_asr_gold.md",
        "full ASR with gold windows spliced",
        "meeting",
        merged,
        extra="gold replaces ASR inside the 4 eval clip windows; rest is GigaAM",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gold", action="store_true", help="also convert eval/ if present (local only)")
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if not FULL_ASR.is_file():
        raise SystemExit(f"missing {FULL_ASR}")
    asr_rows = write_full_asr()
    write_clips_asr()
    if args.gold:
        gold = try_gold()
        if gold is None:
            print("gold skipped: eval/ missing")
        else:
            gold_rows, windows = gold
            write_hybrid(asr_rows, gold_rows, windows)
    chunk_source = OUT / "hybrid_asr_gold.md"
    if not chunk_source.is_file():
        chunk_source = OUT / "full_asr.md"
    write_chunk_dir("D", chunk_source)
    print(f"wrote {OUT} chunks from {chunk_source.name}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Shared Stage 2b helpers: source leaves, timestamps, coverage, merge logs."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
TITLED_CHUNKS = ROOT / "results" / "chunking" / "2" / "attempt_2_chunks_titled.json"
ASR_JSON = ROOT / "results" / "asr" / "2" / "gigaam_v3_rnnt" / "meeting_sample.json"
OUT_DIR = ROOT / "results" / "chunking" / "2b"
LLM_DIR = ROOT / "results" / "llm" / "2b"
WORD_RE = re.compile(r"[a-zа-я0-9]+", re.I)
THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)
TITLE_WORD_RE = re.compile(r"[А-Яа-яЁёA-Za-z0-9]+")

TIMING_SOURCE_AB = "results/chunking/2/attempt_2_chunks_titled.json"
TIMING_SOURCE_CD = "results/asr/2/gigaam_v3_rnnt/meeting_sample.json"
TIMING_METHOD = "source_boundaries"
MAX_DURATION_SEC = 180.0
MAX_IDS_PER_GROUP_AB = 8
PREFERRED_CHAPTERS = (12, 18)
TARGET_CHAPTERS = (8, 20)

METHODS = {
    "title_embed_adjacent",
    "pairwise_llm",
    "pack_across_speakers",
    "late_chunking",
}


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def words(text: str) -> list[str]:
    return WORD_RE.findall((text or "").lower().replace("ё", "е"))


def n_words(text: str) -> int:
    return len(words(text))


def first_last_words(text: str, count: int = 40) -> tuple[str, str]:
    tokens = (text or "").split()
    first = " ".join(tokens[:count])
    last = " ".join(tokens[-count:]) if tokens else ""
    return first, last


def clip_title(text: str) -> str:
    cleaned = THINK_RE.sub("", text or "").strip().strip("\"'«»").strip()
    if not cleaned:
        return ""
    cleaned = cleaned.splitlines()[0].strip().strip("\"'«»").strip()
    tokens = TITLE_WORD_RE.findall(cleaned)
    if len(tokens) <= 10:
        return cleaned
    parts: list[str] = []
    cursor = 0
    for token in tokens[:10]:
        match = re.search(re.escape(token), cleaned[cursor:], re.I)
        if not match:
            parts.append(token)
            continue
        parts.append(cleaned[cursor + match.start() : cursor + match.end()])
        cursor = cursor + match.end()
    return " ".join(parts)


def same_number(a: float, b: float) -> bool:
    return math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=0.0) or float(a) == float(b)


def load_titled_leaves() -> list[dict[str, Any]]:
    payload = json.loads(TITLED_CHUNKS.read_text(encoding="utf-8"))
    leaves = []
    for row in payload["chunks"]:
        leaf_id = int(row["id"])
        text = row.get("text") or ""
        leaves.append(
            {
                "id": leaf_id,
                "start": float(row["start"]),
                "end": float(row["end"]),
                "text": text,
                "speakers": list(row.get("speakers") or []),
                "title": row.get("title") or "",
                "n_words": int(row.get("n_words") or n_words(text)),
            }
        )
    leaves.sort(key=lambda item: item["id"])
    return leaves


def load_asr_leaves() -> list[dict[str, Any]]:
    payload = json.loads(ASR_JSON.read_text(encoding="utf-8"))
    leaves = []
    for row in payload["segments"]:
        text = row.get("text") or ""
        leaves.append(
            {
                "id": int(row["id"]),
                "turn_id": int(row.get("turn_id", row["id"])),
                "piece": int(row.get("piece", 0)),
                "start": float(row["start"]),
                "end": float(row["end"]),
                "text": text,
                "speakers": [row["speaker"]],
                "speaker": row["speaker"],
                "title": "",
                "n_words": n_words(text),
                "empty": not text.strip(),
            }
        )
    leaves.sort(key=lambda item: item["id"])
    return leaves


def expected_ids(leaves: Iterable[dict[str, Any]]) -> list[int]:
    return [int(item["id"]) for item in leaves]


def leaf_index(leaves: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {int(item["id"]): item for item in leaves}


def flatten_source_ids(groups: Iterable[dict[str, Any]]) -> list[int]:
    out: list[int] = []
    for group in groups:
        out.extend(int(x) for x in group["source_ids"])
    return out


def coverage_ok(expected: list[int], covered: list[int]) -> bool:
    return covered == expected


def attach_empty_asr(leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep empty ASR rows; mark a deterministic neighbor (prev, else next)."""
    attached = []
    for index, leaf in enumerate(leaves):
        row = dict(leaf)
        if row.get("empty"):
            row["attach_to"] = "prev" if index > 0 else "next"
        else:
            row["attach_to"] = None
        attached.append(row)
    return attached


def group_from_ids(
    source_ids: list[int],
    index: dict[int, dict[str, Any]],
    title: str = "",
) -> dict[str, Any]:
    if not source_ids:
        raise ValueError("empty source_ids")
    if source_ids != list(range(source_ids[0], source_ids[-1] + 1)):
        raise ValueError(f"non-consecutive source_ids: {source_ids}")
    members = [index[i] for i in source_ids]
    speakers: list[str] = []
    for member in members:
        for speaker in member.get("speakers") or [member.get("speaker")]:
            if speaker and speaker not in speakers:
                speakers.append(speaker)
    text = " ".join((member.get("text") or "").strip() for member in members).strip()
    old_titles = [str(member.get("title") or "") for member in members]
    return {
        "source_ids": list(source_ids),
        "start_source_id": source_ids[0],
        "end_source_id": source_ids[-1],
        "start": float(members[0]["start"]),
        "end": float(members[-1]["end"]),
        "text": text,
        "speakers": speakers,
        "n_words": n_words(text),
        "title": title,
        "old_titles": old_titles,
        "timing_method": TIMING_METHOD,
    }


def chapter_payload(
    groups: list[dict[str, Any]],
    *,
    method: str,
    timing_source: str,
    extra: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    chapters = []
    for idx, group in enumerate(groups):
        row = {
            "id": idx,
            "start": group["start"],
            "end": group["end"],
            "title": group.get("title") or "",
            "leaf_ids": list(group["source_ids"]),
            "source_ids": list(group["source_ids"]),
            "start_source_id": group["start_source_id"],
            "end_source_id": group["end_source_id"],
            "speakers": list(group.get("speakers") or []),
            "n_words": group.get("n_words") or n_words(group.get("text") or ""),
            "text": group.get("text") or "",
            "timing_source": timing_source,
            "timing_method": TIMING_METHOD,
            "method": method,
        }
        if extra:
            row.update(extra)
        chapters.append(row)
    return chapters


def review_sheet(chapters: list[dict[str, Any]], method: str) -> list[dict[str, Any]]:
    sheet = []
    for chapter in chapters:
        sheet.append(
            {
                "method": method,
                "chapter_id": chapter["id"],
                "start": chapter["start"],
                "end": chapter["end"],
                "title": chapter.get("title") or "",
                "source_ids": list(chapter.get("source_ids") or chapter["leaf_ids"]),
                "timing_source": chapter["timing_source"],
                "timing_method": chapter["timing_method"],
            }
        )
    return sheet


def make_op(
    *,
    op: str,
    source_ids: list[int],
    start: float,
    end: float,
    old_titles: list[str] | None = None,
    new_title: str = "",
    reason: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    row = {
        "op": op,
        "source_ids": list(source_ids),
        "start_source_id": source_ids[0],
        "end_source_id": source_ids[-1],
        "start": start,
        "end": end,
        "old_titles": list(old_titles or []),
        "new_title": new_title,
        "reason": reason,
    }
    if extra:
        row.update(extra)
    return row


def write_merge_log(
    path: Path,
    *,
    pass_no: int,
    method: str,
    input_artifact: str,
    timing_source: str,
    num_source: int,
    groups: list[dict[str, Any]],
    expected: list[int],
    ops: list[dict[str, Any]],
    max_ids_per_group: int | None,
    max_duration_sec: float = MAX_DURATION_SEC,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if method not in METHODS:
        raise ValueError(f"unknown merge method: {method}")
    covered = flatten_source_ids(groups)
    payload = {
        "pass": pass_no,
        "method": method,
        "input_artifact": input_artifact,
        "timing_source": timing_source,
        "timing_method": TIMING_METHOD,
        "num_source": num_source,
        "num_after": len(groups),
        "max_duration_sec": max_duration_sec,
        "leaf_ids_expected": expected,
        "leaf_ids_covered": covered,
        "coverage_ok": coverage_ok(expected, covered),
        "ops": ops,
    }
    if max_ids_per_group is not None:
        payload["max_ids_per_group"] = max_ids_per_group
    if extra:
        payload.update(extra)
    write_json(path, payload)
    return payload


def validate_chapters(
    chapters: list[dict[str, Any]],
    leaves: list[dict[str, Any]],
    *,
    timing_source: str,
) -> dict[str, Any]:
    index = leaf_index(leaves)
    expected = expected_ids(leaves)
    errors: list[str] = []
    covered: list[int] = []

    if not chapters:
        errors.append("no chapters")

    prev_end_id = -1
    prev_start = -1.0
    for pos, chapter in enumerate(chapters):
        source_ids = [int(x) for x in (chapter.get("source_ids") or chapter.get("leaf_ids") or [])]
        if not source_ids:
            errors.append(f"chapter {pos}: empty source_ids")
            continue
        if source_ids != list(range(source_ids[0], source_ids[-1] + 1)):
            errors.append(f"chapter {pos}: non-consecutive source_ids {source_ids}")
        for leaf_id in source_ids:
            if leaf_id not in index:
                errors.append(f"chapter {pos}: unknown source id {leaf_id}")
        if source_ids[0] != prev_end_id + 1 and prev_end_id >= 0:
            errors.append(
                f"chapter {pos}: expected start id {prev_end_id + 1}, got {source_ids[0]}"
            )
        if source_ids[0] in index and not same_number(chapter["start"], index[source_ids[0]]["start"]):
            errors.append(
                f"chapter {pos}: start {chapter['start']} != source {index[source_ids[0]]['start']}"
            )
        if source_ids[-1] in index and not same_number(chapter["end"], index[source_ids[-1]]["end"]):
            errors.append(
                f"chapter {pos}: end {chapter['end']} != source {index[source_ids[-1]]['end']}"
            )
        if int(chapter.get("start_source_id", source_ids[0])) != source_ids[0]:
            errors.append(f"chapter {pos}: start_source_id mismatch")
        if int(chapter.get("end_source_id", source_ids[-1])) != source_ids[-1]:
            errors.append(f"chapter {pos}: end_source_id mismatch")
        if chapter.get("timing_source") != timing_source:
            errors.append(f"chapter {pos}: timing_source mismatch")
        if chapter.get("timing_method") != TIMING_METHOD:
            errors.append(f"chapter {pos}: timing_method mismatch")
        if float(chapter["start"]) < prev_start:
            errors.append(f"chapter {pos}: start went backwards")
        prev_start = float(chapter["start"])
        prev_end_id = source_ids[-1]
        covered.extend(source_ids)

    if covered != expected:
        errors.append("coverage mismatch: gaps, duplicates, or reorder")

    return {
        "ok": not errors,
        "errors": errors,
        "n_chapters": len(chapters),
        "leaf_ids_expected": expected,
        "leaf_ids_covered": covered,
        "timing_source": timing_source,
        "timing_method": TIMING_METHOD,
    }


def assert_valid(result: dict[str, Any], label: str) -> None:
    if not result["ok"]:
        raise RuntimeError(f"{label} failed validation: {result['errors']}")


def caps_allow(
    left: dict[str, Any],
    right: dict[str, Any],
    *,
    max_ids: int | None,
    max_duration: float = MAX_DURATION_SEC,
) -> tuple[bool, str]:
    ids = list(left["source_ids"]) + list(right["source_ids"])
    duration = float(right["end"]) - float(left["start"])
    if max_ids is not None and len(ids) > max_ids:
        return False, "cap_ids"
    if duration > max_duration + 1e-12:
        return False, "cap_duration"
    return True, "ok"


def merge_groups(left: dict[str, Any], right: dict[str, Any], title: str) -> dict[str, Any]:
    source_ids = list(left["source_ids"]) + list(right["source_ids"])
    speakers: list[str] = []
    for group in (left, right):
        for speaker in group.get("speakers") or []:
            if speaker not in speakers:
                speakers.append(speaker)
    text = " ".join(
        part for part in [(left.get("text") or "").strip(), (right.get("text") or "").strip()] if part
    )
    return {
        "source_ids": source_ids,
        "start_source_id": source_ids[0],
        "end_source_id": source_ids[-1],
        "start": float(left["start"]),
        "end": float(right["end"]),
        "text": text,
        "speakers": speakers,
        "n_words": n_words(text),
        "title": title,
        "old_titles": [left.get("title") or "", right.get("title") or ""],
        "timing_method": TIMING_METHOD,
    }


def cosine(a: Any, b: Any) -> float:
    return float(a @ b)


def pick_closest_count(rows: list[dict[str, Any]], key: str = "num_chapters") -> dict[str, Any]:
    preferred_mid = sum(PREFERRED_CHAPTERS) / 2
    return min(rows, key=lambda item: (abs(item[key] - preferred_mid), -item[key]))


def inventory() -> dict[str, Any]:
    titled = load_titled_leaves()
    asr = load_asr_leaves()
    empty = [leaf["id"] for leaf in asr if leaf["empty"]]
    return {
        "titled_chunks": {
            "path": TIMING_SOURCE_AB,
            "n": len(titled),
            "ids": expected_ids(titled),
            "start": titled[0]["start"],
            "end": titled[-1]["end"],
            "max_duration_sec": max(leaf["end"] - leaf["start"] for leaf in titled),
        },
        "asr_segments": {
            "path": TIMING_SOURCE_CD,
            "n": len(asr),
            "ids": expected_ids(asr),
            "empty_ids": empty,
            "start": asr[0]["start"],
            "end": asr[-1]["end"],
            "max_duration_sec": max(leaf["end"] - leaf["start"] for leaf in asr),
        },
    }

#!/usr/bin/env python3
"""Adjacent-only Stage 2 chunking with rubert-tiny2 (size/threshold tries only)."""

from __future__ import annotations

import argparse
import json
import re
import statistics
import time
from pathlib import Path
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parents[1]
TRANSCRIPT = ROOT / "results" / "asr" / "2" / "gigaam_v3_rnnt" / "meeting_sample.json"
OUT = ROOT / "results" / "chunking" / "2"
WORD_RE = re.compile(r"[a-zа-я0-9]+", re.I)
SENT_RE = re.compile(r"(?<=[.!?…])\s+")
EMBEDDER = "cointegrated/rubert-tiny2"
LONG_TURN_WORDS = 80
GAP_NEW_CHUNK_SEC = 90.0
TARGET_CHUNKS = (5, 30)
PREFERRED_CHUNKS = 13.5


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def words(text: str) -> list[str]:
    return WORD_RE.findall(text.lower().replace("ё", "е"))


def n_words(text: str) -> int:
    return len(words(text))


def split_long_text(text: str, start: float, end: float, speaker: str) -> list[dict[str, Any]]:
    tokens = words(text)
    if len(tokens) <= LONG_TURN_WORDS:
        return [{"start": start, "end": end, "speaker": speaker, "text": text.strip()}]
    parts = [part.strip() for part in SENT_RE.split(text) if part.strip()]
    if len(parts) <= 1:
        # Fall back to ~40-word windows without cutting mid-token.
        parts = []
        chunk: list[str] = []
        raw_tokens = text.split()
        for token in raw_tokens:
            chunk.append(token)
            if n_words(" ".join(chunk)) >= 40:
                parts.append(" ".join(chunk))
                chunk = []
        if chunk:
            parts.append(" ".join(chunk))
    total = max(sum(n_words(part) for part in parts), 1)
    cursor = start
    duration = max(end - start, 1e-6)
    rows = []
    for index, part in enumerate(parts):
        share = n_words(part) / total
        piece_end = end if index == len(parts) - 1 else cursor + duration * share
        rows.append(
            {
                "start": cursor,
                "end": piece_end,
                "speaker": speaker,
                "text": part,
            }
        )
        cursor = piece_end
    return rows


def speaker_turns(segments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, list[dict[str, Any]]] = {}
    order: list[int] = []
    for segment in segments:
        turn_id = int(segment.get("turn_id", segment["id"]))
        grouped.setdefault(turn_id, []).append(segment)
        if turn_id not in order:
            order.append(turn_id)
    turns: list[dict[str, Any]] = []
    for turn_id in order:
        pieces = sorted(grouped[turn_id], key=lambda item: item["start"])
        speaker = pieces[0]["speaker"]
        text = " ".join(item["text"].strip() for item in pieces if item["text"].strip()).strip()
        start = float(pieces[0]["start"])
        end = float(pieces[-1]["end"])
        if n_words(text) > LONG_TURN_WORDS and len(pieces) > 1:
            for piece in pieces:
                turns.extend(
                    split_long_text(
                        piece["text"],
                        float(piece["start"]),
                        float(piece["end"]),
                        speaker,
                    )
                )
        else:
            turns.extend(split_long_text(text, start, end, speaker))
    return [turn for turn in turns if turn["text"].strip()]


def pack_units(
    turns: list[dict[str, Any]],
    min_words: int,
    max_words: int,
) -> list[dict[str, Any]]:
    units: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_count = 0
    for turn in turns:
        count = n_words(turn["text"])
        if not current:
            current = [turn]
            current_count = count
            continue
        same_speaker = turn["speaker"] == current[-1]["speaker"]
        would = current_count + count
        if same_speaker and not (current_count >= min_words and would > max_words):
            current.append(turn)
            current_count = would
        else:
            units.append(current)
            current = [turn]
            current_count = count
    if current:
        units.append(current)
    result = []
    for index, group in enumerate(units):
        text = " ".join(item["text"].strip() for item in group).strip()
        result.append(
            {
                "id": index,
                "start": float(group[0]["start"]),
                "end": float(group[-1]["end"]),
                "speakers": sorted({item["speaker"] for item in group}),
                "text": text,
                "n_words": n_words(text),
                "n_turns": len(group),
            }
        )
    return result


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b))


def merge_with_model(
    units: list[dict[str, Any]],
    model: SentenceTransformer,
    threshold: float,
) -> tuple[list[dict[str, Any]], list[float], list[dict[str, Any]]]:
    if not units:
        return [], [], []
    chunks: list[list[int]] = [[0]]
    accepted: list[float] = []
    decisions: list[dict[str, Any]] = []
    current_vec = model.encode(
        [units[0]["text"]],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]
    for index in range(1, len(units)):
        gap = units[index]["start"] - units[chunks[-1][-1]]["end"]
        if gap > GAP_NEW_CHUNK_SEC:
            decisions.append(
                {
                    "next_unit": index,
                    "reason": "gap",
                    "gap_sec": round(float(gap), 3),
                    "cosine": None,
                    "merged": False,
                }
            )
            chunks.append([index])
            current_vec = model.encode(
                [units[index]["text"]],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]
            continue
        next_vec = model.encode(
            [units[index]["text"]],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        score = cosine(current_vec, next_vec)
        if score >= threshold:
            chunks[-1].append(index)
            accepted.append(score)
            current_text = " ".join(units[member]["text"] for member in chunks[-1])
            current_vec = model.encode(
                [current_text],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]
            decisions.append(
                {
                    "next_unit": index,
                    "reason": "cosine",
                    "gap_sec": round(float(gap), 3),
                    "cosine": round(score, 6),
                    "merged": True,
                }
            )
        else:
            chunks.append([index])
            current_vec = next_vec
            decisions.append(
                {
                    "next_unit": index,
                    "reason": "cosine",
                    "gap_sec": round(float(gap), 3),
                    "cosine": round(score, 6),
                    "merged": False,
                }
            )
    result = []
    for chunk_id, members in enumerate(chunks):
        group = [units[index] for index in members]
        text = " ".join(item["text"] for item in group).strip()
        speakers: list[str] = []
        for item in group:
            for speaker in item["speakers"]:
                if speaker not in speakers:
                    speakers.append(speaker)
        result.append(
            {
                "id": chunk_id,
                "start": group[0]["start"],
                "end": group[-1]["end"],
                "text": text,
                "speakers": speakers,
                "n_words": n_words(text),
                "n_units": len(group),
            }
        )
    return result, accepted, decisions


def cosine_stats(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None, "n_accepted": 0}
    return {
        "min": round(min(values), 6),
        "median": round(float(statistics.median(values)), 6),
        "max": round(max(values), 6),
        "n_accepted": len(values),
    }


def in_range(num_chunks: int) -> bool:
    return TARGET_CHUNKS[0] <= num_chunks <= TARGET_CHUNKS[1]


def next_recipe(attempt: int, num_chunks: int) -> tuple[int, int, float]:
    """Only unit size band and/or cosine threshold may change."""
    if num_chunks < TARGET_CHUNKS[0]:
        # One blob: smaller units + higher threshold.
        if attempt == 1:
            return 8, 20, 0.88
        return 5, 15, 0.92
    # Too many scraps: larger units + lower threshold.
    if attempt == 1:
        return 40, 80, 0.70
    return 60, 120, 0.65


def run_attempt(
    turns: list[dict[str, Any]],
    model: SentenceTransformer,
    min_words: int,
    max_words: int,
    threshold: float,
    attempt: int,
) -> dict[str, Any]:
    units = pack_units(turns, min_words, max_words)
    started = time.monotonic()
    chunks, accepted, decisions = merge_with_model(units, model, threshold)
    runtime_sec = round(time.monotonic() - started, 3)
    stats = cosine_stats(accepted)
    payload = {
        "execution_mode": "local",
        "provider": "sentence-transformers",
        "embedding_model": EMBEDDER,
        "input_artifact": str(TRANSCRIPT.relative_to(ROOT)),
        "attempt": attempt,
        "unit_size": {"min_words": min_words, "max_words": max_words},
        "threshold": threshold,
        "num_units": len(units),
        "num_chunks": len(chunks),
        "embed_runtime_sec": runtime_sec,
        "accepted_merge_cosine": stats,
        "in_target_range": in_range(len(chunks)),
        "units": units,
        "chunks": chunks,
        "decisions": decisions,
    }
    write_json(OUT / f"attempt_{attempt}.json", payload)
    return payload


def pick_for_titles(attempts: list[dict[str, Any]]) -> dict[str, Any] | None:
    good = [item for item in attempts if in_range(item["num_chunks"])]
    if not good:
        return None
    return min(good, key=lambda item: abs(item["num_chunks"] - PREFERRED_CHUNKS))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", type=Path, default=TRANSCRIPT)
    args = parser.parse_args()
    source = json.loads(args.transcript.read_text(encoding="utf-8"))
    turns = speaker_turns(source["segments"])
    started = time.monotonic()
    model = SentenceTransformer(EMBEDDER, device="cpu")
    load_sec = round(time.monotonic() - started, 3)

    attempts: list[dict[str, Any]] = []
    min_words, max_words, threshold = 20, 50, 0.80
    for attempt in range(1, 4):
        payload = run_attempt(turns, model, min_words, max_words, threshold, attempt)
        attempts.append(payload)
        print(
            json.dumps(
                {
                    "attempt": attempt,
                    "unit_size": [min_words, max_words],
                    "threshold": threshold,
                    "num_chunks": payload["num_chunks"],
                    "embed_runtime_sec": payload["embed_runtime_sec"],
                    "accepted_merge_cosine": payload["accepted_merge_cosine"],
                },
                ensure_ascii=False,
            )
        )
        if in_range(payload["num_chunks"]):
            break
        if attempt == 3:
            break
        min_words, max_words, threshold = next_recipe(attempt, payload["num_chunks"])

    selected = pick_for_titles(attempts)
    summary = {
        "execution_mode": "local",
        "embedding_model": EMBEDDER,
        "model_load_sec": load_sec,
        "speaker_turns": len(turns),
        "attempts": [
            {
                "attempt": item["attempt"],
                "unit_size": item["unit_size"],
                "threshold": item["threshold"],
                "num_chunks": item["num_chunks"],
                "embed_runtime_sec": item["embed_runtime_sec"],
                "accepted_merge_cosine": item["accepted_merge_cosine"],
                "in_target_range": item["in_target_range"],
            }
            for item in attempts
        ],
        "selected_attempt": selected["attempt"] if selected else None,
        "selected_num_chunks": selected["num_chunks"] if selected else None,
        "titles_allowed": selected is not None,
    }
    write_json(OUT / "_summary.json", summary)
    if selected:
        write_json(
            OUT / "chunks.json",
            {
                "execution_mode": "local",
                "provider": "sentence-transformers",
                "embedding_model": EMBEDDER,
                "input_artifact": str(args.transcript.relative_to(ROOT))
                if args.transcript.is_relative_to(ROOT)
                else str(args.transcript),
                "attempt": selected["attempt"],
                "unit_size": selected["unit_size"],
                "threshold": selected["threshold"],
                "num_chunks": selected["num_chunks"],
                "embed_runtime_sec": selected["embed_runtime_sec"],
                "accepted_merge_cosine": selected["accepted_merge_cosine"],
                "chunks": [
                    {
                        "id": chunk["id"],
                        "start": chunk["start"],
                        "end": chunk["end"],
                        "text": chunk["text"],
                        "speakers": chunk["speakers"],
                        "n_words": chunk["n_words"],
                    }
                    for chunk in selected["chunks"]
                ],
            },
        )
    print(json.dumps({"selected_attempt": summary["selected_attempt"], "titles_allowed": summary["titles_allowed"]}))


if __name__ == "__main__":
    main()

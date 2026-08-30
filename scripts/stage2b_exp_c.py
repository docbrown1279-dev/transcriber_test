#!/usr/bin/env python3
"""Experiment C: cross-speaker packing + one tiny2 adjacent pass (40-80 / 0.70)."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import argparse
import json
import time
from typing import Any

from sentence_transformers import SentenceTransformer

from stage2b_common import (
    MAX_DURATION_SEC,
    OUT_DIR,
    TIMING_SOURCE_CD,
    attach_empty_asr,
    assert_valid,
    chapter_payload,
    cosine,
    expected_ids,
    load_asr_leaves,
    make_op,
    n_words,
    review_sheet,
    validate_chapters,
    write_json,
    write_merge_log,
)
from stage2b_exp_a import embed_titles, group_by_threshold

EMBEDDER = "cointegrated/rubert-tiny2"
MIN_WORDS = 40
MAX_WORDS = 80
THRESHOLD = 0.70
LONG_TURN_WORDS = 80
CROSS_SPEAKER_GAP_SEC = 2.0
TITLE_THRESHOLDS = (0.85, 0.80, 0.75)


def _piece_from(members: list[dict[str, Any]]) -> dict[str, Any]:
    source_ids = [item["id"] for item in members]
    return {
        "source_ids": source_ids,
        "start": members[0]["start"],
        "end": members[-1]["end"],
        "text": " ".join(item["text"].strip() for item in members if item["text"].strip()).strip(),
        "speakers": [members[0]["speaker"]],
        "n_words": sum(item["n_words"] for item in members if not item.get("empty")),
    }


def build_pieces(leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Whole turns unless the turn exceeds ~80 words; then keep source pieces."""
    attached = attach_empty_asr(leaves)
    by_turn: dict[int, list[dict[str, Any]]] = {}
    order: list[int] = []
    for leaf in attached:
        turn_id = int(leaf["turn_id"])
        by_turn.setdefault(turn_id, []).append(leaf)
        if turn_id not in order:
            order.append(turn_id)

    pieces: list[dict[str, Any]] = []
    pending_empty: list[dict[str, Any]] = []
    for turn_id in order:
        members = sorted(by_turn[turn_id], key=lambda item: (item["start"], item["id"]))
        nonempty = [item for item in members if not item.get("empty")]
        word_count = sum(item["n_words"] for item in nonempty)
        if pending_empty:
            members = pending_empty + members
            pending_empty = []
        if word_count > LONG_TURN_WORDS and len(nonempty) > 1:
            current: list[dict[str, Any]] = []
            for item in members:
                if item.get("empty") and not current:
                    if pieces:
                        pieces[-1]["source_ids"].append(item["id"])
                        pieces[-1]["end"] = item["end"]
                    else:
                        current.append(item)
                    continue
                if item.get("empty"):
                    current.append(item)
                    continue
                if current and any(not row.get("empty") for row in current):
                    pieces.append(_piece_from(current))
                    current = [item]
                else:
                    current.append(item)
            if current:
                if any(not row.get("empty") for row in current):
                    pieces.append(_piece_from(current))
                else:
                    pending_empty.extend(current)
        else:
            pieces.append(_piece_from(members))
    if pending_empty and pieces:
        pieces[-1]["source_ids"].extend(item["id"] for item in pending_empty)
        pieces[-1]["end"] = pending_empty[-1]["end"]
    elif pending_empty:
        pieces.append(_piece_from(pending_empty))
    return pieces


def pack_units(pieces: list[dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    current_words = 0
    for piece in pieces:
        count = piece["n_words"]
        if not current:
            current = [piece]
            current_words = count
            continue
        gap = float(piece["start"]) - float(current[-1]["end"])
        same_speaker = piece["speakers"][0] == current[-1]["speakers"][0]
        cross_ok = same_speaker or gap <= CROSS_SPEAKER_GAP_SEC
        would = current_words + count
        if cross_ok and not (current_words >= MIN_WORDS and would > MAX_WORDS):
            current.append(piece)
            current_words = would
        else:
            units.append(current)
            current = [piece]
            current_words = count
    if current:
        units.append(current)
    result = []
    for group in units:
        source_ids = [leaf_id for piece in group for leaf_id in piece["source_ids"]]
        speakers: list[str] = []
        for piece in group:
            for speaker in piece["speakers"]:
                if speaker not in speakers:
                    speakers.append(speaker)
        text = " ".join(piece["text"].strip() for piece in group if piece["text"].strip()).strip()
        result.append(
            {
                "source_ids": source_ids,
                "start_source_id": source_ids[0],
                "end_source_id": source_ids[-1],
                "start": float(group[0]["start"]),
                "end": float(group[-1]["end"]),
                "text": text,
                "speakers": speakers,
                "n_words": n_words(text),
                "title": "",
                "old_titles": [],
            }
        )
    return result


def merge_units(
    units: list[dict[str, Any]],
    model: SentenceTransformer,
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float]]:
    if not units:
        return [], [], []
    chunks: list[list[int]] = [[0]]
    ops: list[dict[str, Any]] = []
    accepted: list[float] = []
    current_vec = model.encode(
        [units[0]["text"] or " "],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]
    for index in range(1, len(units)):
        next_vec = model.encode(
            [units[index]["text"] or " "],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        score = cosine(current_vec, next_vec)
        trial_ids = []
        for member in chunks[-1] + [index]:
            trial_ids.extend(units[member]["source_ids"])
        duration = float(units[index]["end"]) - float(units[chunks[-1][0]]["start"])
        if score >= threshold and duration <= MAX_DURATION_SEC + 1e-12:
            chunks[-1].append(index)
            accepted.append(score)
            current_text = " ".join(units[member]["text"] for member in chunks[-1])
            current_vec = model.encode(
                [current_text or " "],
                normalize_embeddings=True,
                show_progress_bar=False,
            )[0]
            source_ids = [leaf_id for member in chunks[-1] for leaf_id in units[member]["source_ids"]]
            ops.append(
                make_op(
                    op="merge",
                    source_ids=source_ids,
                    start=units[chunks[-1][0]]["start"],
                    end=units[index]["end"],
                    old_titles=[],
                    new_title="",
                    reason="same_topic",
                    extra={"cosine": round(float(score), 6), "unit_pair": [index - 1, index]},
                )
            )
        else:
            reason = "low_cosine" if score < threshold else "cap_duration"
            source_ids = [leaf_id for member in chunks[-1] for leaf_id in units[member]["source_ids"]]
            ops.append(
                make_op(
                    op="keep",
                    source_ids=source_ids,
                    start=units[chunks[-1][0]]["start"],
                    end=units[chunks[-1][-1]]["end"],
                    old_titles=[],
                    new_title="",
                    reason=reason,
                    extra={"cosine": round(float(score), 6), "unit_pair": [index - 1, index]},
                )
            )
            chunks.append([index])
            current_vec = next_vec
    result = []
    for members in chunks:
        source_ids = [leaf_id for member in members for leaf_id in units[member]["source_ids"]]
        speakers: list[str] = []
        for member in members:
            for speaker in units[member]["speakers"]:
                if speaker not in speakers:
                    speakers.append(speaker)
        text = " ".join(units[member]["text"] for member in members).strip()
        result.append(
            {
                "source_ids": source_ids,
                "start_source_id": source_ids[0],
                "end_source_id": source_ids[-1],
                "start": units[members[0]]["start"],
                "end": units[members[-1]]["end"],
                "text": text,
                "speakers": speakers,
                "n_words": n_words(text),
                "title": "",
                "old_titles": [],
            }
        )
    return result, ops, accepted


def title_embed_units(groups: list[dict[str, Any]], model: SentenceTransformer) -> dict[str, Any]:
    """One Experiment A protocol pass over C titles (caps: 8 C-units, 180s)."""
    fake_leaves = []
    for idx, group in enumerate(groups):
        fake_leaves.append(
            {
                "id": idx,
                "start": group["start"],
                "end": group["end"],
                "text": group["text"],
                "speakers": group["speakers"],
                "title": group.get("title") or "",
                "n_words": group["n_words"],
                "source_ids": group["source_ids"],
            }
        )
    embeddings = embed_titles([leaf["title"] or " " for leaf in fake_leaves], model)
    scored = []
    for threshold in TITLE_THRESHOLDS:
        merged, ops, accepted = group_by_threshold(fake_leaves, embeddings, threshold)
        # Map fake ids back to ASR source ids.
        remapped = []
        for group in merged:
            asr_ids: list[int] = []
            for fake_id in group["source_ids"]:
                asr_ids.extend(groups[fake_id]["source_ids"])
            remapped.append(
                {
                    "source_ids": asr_ids,
                    "start_source_id": asr_ids[0],
                    "end_source_id": asr_ids[-1],
                    "start": group["start"],
                    "end": group["end"],
                    "text": group["text"],
                    "speakers": group["speakers"],
                    "n_words": group["n_words"],
                    "title": group.get("title") or "",
                    "old_titles": group.get("old_titles") or [],
                }
            )
        remapped_ops = []
        for op in ops:
            asr_ids = []
            for fake_id in op["source_ids"]:
                asr_ids.extend(groups[int(fake_id)]["source_ids"])
            row = dict(op)
            row["source_ids"] = asr_ids
            row["start_source_id"] = asr_ids[0]
            row["end_source_id"] = asr_ids[-1]
            remapped_ops.append(row)
        ops = remapped_ops
        scored.append(
            {
                "threshold": threshold,
                "num_chapters": len(remapped),
                "groups": remapped,
                "ops": ops,
                "accepted": accepted,
            }
        )
    preferred_mid = 15.0
    selected = min(scored, key=lambda item: (abs(item["num_chapters"] - preferred_mid), -item["num_chapters"]))
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    leaves = load_asr_leaves()
    expected = expected_ids(leaves)
    pieces = build_pieces(leaves)
    units = pack_units(pieces)
    started = time.monotonic()
    model = SentenceTransformer(EMBEDDER, device=args.device)
    groups, ops, accepted = merge_units(units, model, THRESHOLD)
    runtime = round(time.monotonic() - started, 3)
    chapters = chapter_payload(groups, method="pack_across_speakers", timing_source=TIMING_SOURCE_CD)
    validation = validate_chapters(chapters, leaves, timing_source=TIMING_SOURCE_CD)
    assert_valid(validation, "exp C pack")
    log = write_merge_log(
        OUT_DIR / "merge_log_c_pack.json",
        pass_no=6,
        method="pack_across_speakers",
        input_artifact=TIMING_SOURCE_CD,
        timing_source=TIMING_SOURCE_CD,
        num_source=len(leaves),
        groups=groups,
        expected=expected,
        ops=ops,
        max_ids_per_group=None,
        extra={
            "experiment": "C",
            "unit_size": {"min_words": MIN_WORDS, "max_words": MAX_WORDS},
            "threshold": THRESHOLD,
            "cross_speaker_gap_sec": CROSS_SPEAKER_GAP_SEC,
            "n_pieces": len(pieces),
            "n_units": len(units),
        },
    )
    write_json(OUT_DIR / "merge_log_pass6.json", log)
    write_json(OUT_DIR / "validation_c_pack.json", validation)
    write_json(
        OUT_DIR / "exp_c_pack.json",
        {
            "experiment": "C",
            "stage": "pack_tiny2",
            "embedding_model": EMBEDDER,
            "threshold": THRESHOLD,
            "num_pieces": len(pieces),
            "num_units": len(units),
            "num_chapters": len(chapters),
            "embed_runtime_sec": runtime,
            "accepted_merge_cosine": {
                "min": min(accepted) if accepted else None,
                "max": max(accepted) if accepted else None,
                "n_accepted": len(accepted),
            },
            "chapters": chapters,
            "validation": validation,
            "titles_allowed": 8 <= len(chapters) <= 40,
            "title_embed_pending": len(chapters) > 20,
        },
    )
    write_json(
        OUT_DIR / "exp_c_chapters.json",
        {
            "experiment": "C",
            "execution_mode": "local",
            "provider": "sentence-transformers",
            "embedding_model": EMBEDDER,
            "input_artifact": TIMING_SOURCE_CD,
            "timing_source": TIMING_SOURCE_CD,
            "timing_method": "source_boundaries",
            "num_chapters": len(chapters),
            "chapters": chapters,
            "title_embed_applied": False,
        },
    )
    write_json(
        OUT_DIR / "review_sheet_c.json",
        {"experiment": "C", "rows": review_sheet(chapters, "pack_across_speakers")},
    )
    print(
        json.dumps(
            {
                "experiment": "C",
                "num_pieces": len(pieces),
                "num_units": len(units),
                "num_chapters": len(chapters),
                "titles_allowed": 8 <= len(chapters) <= 40,
                "title_embed_pending": len(chapters) > 20,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

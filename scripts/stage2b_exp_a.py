#!/usr/bin/env python3
"""Experiment A: adjacent title embeddings with rubert-tiny2. No LLM grouping."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import argparse
import time
from typing import Any

import numpy as np
from sentence_transformers import SentenceTransformer

from stage2b_common import (
    MAX_DURATION_SEC,
    MAX_IDS_PER_GROUP_AB,
    OUT_DIR,
    TIMING_SOURCE_AB,
    assert_valid,
    cosine,
    expected_ids,
    group_from_ids,
    inventory,
    leaf_index,
    load_titled_leaves,
    make_op,
    pick_closest_count,
    validate_chapters,
    write_json,
    write_merge_log,
    chapter_payload,
    review_sheet,
)

EMBEDDER = "cointegrated/rubert-tiny2"
THRESHOLDS = (0.85, 0.80, 0.75)
PASS_NOS = {0.85: 1, 0.80: 2, 0.75: 3}


def embed_titles(titles: list[str], model: SentenceTransformer) -> np.ndarray:
    return model.encode(titles, normalize_embeddings=True, show_progress_bar=False)


def group_by_threshold(
    leaves: list[dict[str, Any]],
    embeddings: np.ndarray,
    threshold: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[float]]:
    index = leaf_index(leaves)
    current = [leaves[0]["id"]]
    runs: list[list[int]] = []
    ops: list[dict[str, Any]] = []
    accepted: list[float] = []
    for i in range(1, len(leaves)):
        prev_id = leaves[i - 1]["id"]
        next_id = leaves[i]["id"]
        score = cosine(embeddings[i - 1], embeddings[i])
        trial = current + [next_id]
        duration = float(leaves[i]["end"]) - float(index[current[0]]["start"])
        cap_ids = len(trial) <= MAX_IDS_PER_GROUP_AB
        cap_dur = duration <= MAX_DURATION_SEC + 1e-12
        if score >= threshold and cap_ids and cap_dur:
            current.append(next_id)
            accepted.append(score)
            old_titles = [index[j].get("title") or "" for j in current]
            merged = group_from_ids(current, index, title=" | ".join(old_titles))
            ops.append(
                make_op(
                    op="merge",
                    source_ids=list(current),
                    start=merged["start"],
                    end=merged["end"],
                    old_titles=old_titles,
                    new_title=merged["title"],
                    reason="same_topic",
                    extra={"cosine": round(float(score), 6), "pair": [prev_id, next_id]},
                )
            )
        else:
            reason = "low_cosine"
            if score >= threshold and not cap_ids:
                reason = "cap_ids"
            elif score >= threshold and not cap_dur:
                reason = "cap_duration"
            kept = group_from_ids(current, index, title=index[current[0]].get("title") or "")
            ops.append(
                make_op(
                    op="keep",
                    source_ids=list(current),
                    start=kept["start"],
                    end=kept["end"],
                    old_titles=[index[j].get("title") or "" for j in current],
                    new_title=kept["title"],
                    reason=reason,
                    extra={"cosine": round(float(score), 6), "pair": [prev_id, next_id]},
                )
            )
            runs.append(list(current))
            current = [next_id]
    runs.append(list(current))
    groups = [
        group_from_ids(run, index, title=" | ".join(index[i].get("title") or "" for i in run))
        for run in runs
    ]
    return groups, ops, accepted


def run_threshold(
    leaves: list[dict[str, Any]],
    embeddings: np.ndarray,
    threshold: float,
) -> dict[str, Any]:
    groups, ops, accepted = group_by_threshold(leaves, embeddings, threshold)
    expected = expected_ids(leaves)
    tag = f"{threshold:.2f}".replace(".", "")
    chapters = chapter_payload(groups, method="title_embed_adjacent", timing_source=TIMING_SOURCE_AB)
    validation = validate_chapters(chapters, leaves, timing_source=TIMING_SOURCE_AB)
    assert_valid(validation, f"exp A t={threshold}")
    artifact = OUT_DIR / f"exp_a_t{tag}.json"
    log_named = OUT_DIR / f"merge_log_a_t{tag}.json"
    log_pass = OUT_DIR / f"merge_log_pass{PASS_NOS[threshold]}.json"
    payload = {
        "experiment": "A",
        "execution_mode": "local",
        "provider": "sentence-transformers",
        "embedding_model": EMBEDDER,
        "input_artifact": TIMING_SOURCE_AB,
        "timing_source": TIMING_SOURCE_AB,
        "timing_method": "source_boundaries",
        "threshold": threshold,
        "max_ids_per_group": MAX_IDS_PER_GROUP_AB,
        "max_duration_sec": MAX_DURATION_SEC,
        "num_source": len(leaves),
        "num_chapters": len(chapters),
        "accepted_merge_cosine": {
            "min": min(accepted) if accepted else None,
            "median": sorted(accepted)[len(accepted) // 2] if accepted else None,
            "max": max(accepted) if accepted else None,
            "n_accepted": len(accepted),
        },
        "chapters": chapters,
        "validation": validation,
    }
    write_json(artifact, payload)
    log = write_merge_log(
        log_named,
        pass_no=PASS_NOS[threshold],
        method="title_embed_adjacent",
        input_artifact=TIMING_SOURCE_AB,
        timing_source=TIMING_SOURCE_AB,
        num_source=len(leaves),
        groups=groups,
        expected=expected,
        ops=ops,
        max_ids_per_group=MAX_IDS_PER_GROUP_AB,
        extra={"threshold": threshold, "experiment": "A"},
    )
    write_json(log_pass, log)
    write_json(OUT_DIR / f"validation_a_t{tag}.json", validation)
    if not log["coverage_ok"]:
        raise RuntimeError(f"exp A t={threshold} coverage failed")
    return payload


def select_and_write(results: list[dict[str, Any]]) -> dict[str, Any]:
    selected = pick_closest_count(results)
    tag = f"{selected['threshold']:.2f}".replace(".", "")
    chapters = selected["chapters"]
    write_json(OUT_DIR / "exp_a_selected.json", selected)
    write_json(OUT_DIR / "exp_a_chapters.json", {"experiment": "A", "threshold": selected["threshold"], "chapters": chapters})
    write_json(
        OUT_DIR / "review_sheet_a.json",
        {
            "experiment": "A",
            "selected_threshold": selected["threshold"],
            "rows": review_sheet(chapters, "title_embed_adjacent"),
        },
    )
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    write_json(OUT_DIR / "inventory.json", inventory())
    leaves = load_titled_leaves()
    started = time.monotonic()
    model = SentenceTransformer(EMBEDDER, device=args.device)
    embeddings = embed_titles([leaf.get("title") or "" for leaf in leaves], model)
    load_sec = round(time.monotonic() - started, 3)
    results = [run_threshold(leaves, embeddings, threshold) for threshold in THRESHOLDS]
    selected = select_and_write(results)
    summary = {
        "experiment": "A",
        "embedding_model": EMBEDDER,
        "model_load_and_embed_sec": load_sec,
        "thresholds": [
            {"threshold": row["threshold"], "num_chapters": row["num_chapters"]} for row in results
        ],
        "selected_threshold": selected["threshold"],
        "selected_num_chapters": selected["num_chapters"],
        "titles_pending": True,
    }
    write_json(OUT_DIR / "exp_a_summary.json", summary)
    print(json_dumps(summary))


def json_dumps(value: Any) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    main()

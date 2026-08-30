#!/usr/bin/env python3
"""Experiment D: late chunking with jina-embeddings-v3 over immutable ASR atoms."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import argparse
import json
import time
from typing import Any

import numpy as np
import torch

from stage2b_common import (
    MAX_DURATION_SEC,
    OUT_DIR,
    TIMING_SOURCE_CD,
    attach_empty_asr,
    assert_valid,
    chapter_payload,
    cosine,
    expected_ids,
    group_from_ids,
    leaf_index,
    load_asr_leaves,
    make_op,
    n_words,
    review_sheet,
    validate_chapters,
    write_json,
    write_merge_log,
)

MODEL_ID = "jinaai/jina-embeddings-v3"
NATIVE_MODEL_ID = "jinaai/jina-embeddings-v3-hf"
WINDOW_SEC = 240.0
OVERLAP_SEC = 60.0
HOP_SEC = WINDOW_SEC - OVERLAP_SEC
MIN_CHAPTER_SEC = 45.0
PREF_MIN_SEC = 75.0
PREF_MAX_SEC = 150.0
MAX_TOKENS = 8192
ALTERNATIVES = [
    {
        "model": "Alibaba-NLP/gte-multilingual-base",
        "params": "305M",
        "ctx": 8192,
        "executed": False,
    },
    {
        "model": "BAAI/bge-m3",
        "params": "568M",
        "ctx": 8192,
        "executed": False,
    },
    {
        "model": "Qwen/Qwen3-Embedding-0.6B",
        "params": "0.6B",
        "ctx": 32000,
        "executed": False,
        "note": "long-context capable; token-span pooling is less canonical for late chunking",
    },
]


def load_jina(device: str) -> tuple[Any, Any, str, str]:
    try:
        from transformers import AutoModel, AutoTokenizer
    except ImportError as exc:
        raise RuntimeError(f"missing dependency: {exc}") from exc
    errors: list[str] = []
    for repo, trust in ((MODEL_ID, True), (NATIVE_MODEL_ID, False)):
        try:
            tokenizer = AutoTokenizer.from_pretrained(repo, trust_remote_code=trust)
            model = AutoModel.from_pretrained(repo, trust_remote_code=trust)
            model.eval()
            model.to(device)
            note = (
                "official custom-code checkpoint"
                if repo == MODEL_ID
                else (
                    "native Transformers port of the same Jina XLM-RoBERTa 570M / 8192-token model; "
                    f"{MODEL_ID} failed on transformers 5.16.1 "
                    "(custom flash code: all_tied_weights_keys)"
                )
            )
            return tokenizer, model, repo, note
        except Exception as exc:
            errors.append(f"{repo}: {type(exc).__name__}: {exc}")
            continue
    raise RuntimeError(" ; ".join(errors))


def window_starts(t0: float, t1: float) -> list[float]:
    starts = []
    cursor = t0
    while cursor < t1:
        starts.append(cursor)
        cursor += HOP_SEC
    if not starts:
        starts.append(t0)
    return starts


def atoms_in_window(atoms: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [atom for atom in atoms if atom["start"] < end and atom["end"] > start]


def tokenize_window(tokenizer: Any, texts: list[str]) -> tuple[list[int], list[tuple[int, int] | None]]:
    cls_id = tokenizer.cls_token_id
    sep_id = tokenizer.sep_token_id
    if cls_id is None:
        cls_id = tokenizer.bos_token_id or 0
    if sep_id is None:
        sep_id = tokenizer.eos_token_id or cls_id
    ids = [int(cls_id)]
    spans: list[tuple[int, int] | None] = []
    for text in texts:
        piece = tokenizer.encode(text or "", add_special_tokens=False)
        start = len(ids)
        ids.extend(int(x) for x in piece)
        end = len(ids)
        spans.append((start, end) if piece else None)
    ids.append(int(sep_id))
    return ids, spans


def encode_hidden(model: Any, input_ids: list[int], device: str) -> torch.Tensor:
    tensor = torch.tensor([input_ids], dtype=torch.long, device=device)
    mask = torch.ones_like(tensor)
    kwargs: dict[str, Any] = {"input_ids": tensor, "attention_mask": mask}
    with torch.no_grad():
        try:
            out = model(**kwargs, task="text-matching")
        except TypeError:
            try:
                out = model(**kwargs)
            except TypeError:
                out = model(input_ids=tensor, attention_mask=mask)
    hidden = out.last_hidden_state[0]
    return hidden


def mean_pool(hidden: torch.Tensor, span: tuple[int, int] | None) -> np.ndarray | None:
    if span is None:
        return None
    start, end = span
    end = min(end, hidden.size(0))
    start = min(start, end)
    if end <= start:
        return None
    vec = hidden[start:end].mean(dim=0)
    vec = torch.nn.functional.normalize(vec, dim=0)
    return vec.detach().cpu().numpy()


def collect_boundary_scores(
    atoms: list[dict[str, Any]],
    tokenizer: Any,
    model: Any,
    device: str,
) -> tuple[list[float], dict[str, Any]]:
    n = len(atoms)
    buckets: list[list[float]] = [[] for _ in range(max(n - 1, 0))]
    t0 = atoms[0]["start"]
    t1 = atoms[-1]["end"]
    windows_meta = []
    for w_start in window_starts(t0, t1):
        w_end = w_start + WINDOW_SEC
        window_atoms = atoms_in_window(atoms, w_start, w_end)
        if len(window_atoms) < 2:
            windows_meta.append(
                {
                    "start": w_start,
                    "end": w_end,
                    "n_atoms": len(window_atoms),
                    "n_tokens": 0,
                    "skipped": "too_few_atoms",
                }
            )
            continue
        ids, spans = tokenize_window(tokenizer, [atom.get("text") or "" for atom in window_atoms])
        if len(ids) > MAX_TOKENS:
            windows_meta.append(
                {
                    "start": w_start,
                    "end": w_end,
                    "n_atoms": len(window_atoms),
                    "n_tokens": len(ids),
                    "skipped": "token_limit",
                }
            )
            continue
        hidden = encode_hidden(model, ids, device)
        vectors: dict[int, np.ndarray] = {}
        for atom, span in zip(window_atoms, spans):
            vec = mean_pool(hidden, span)
            if vec is not None:
                vectors[atom["id"]] = vec
        pairs = 0
        for left, right in zip(window_atoms, window_atoms[1:]):
            if right["id"] != left["id"] + 1:
                continue
            boundary = left["id"]
            if left.get("empty") or right.get("empty"):
                buckets[boundary].append(1.0)
                pairs += 1
                continue
            if left["id"] in vectors and right["id"] in vectors:
                buckets[boundary].append(cosine(vectors[left["id"]], vectors[right["id"]]))
                pairs += 1
        windows_meta.append(
            {
                "start": w_start,
                "end": w_end,
                "n_atoms": len(window_atoms),
                "n_tokens": len(ids),
                "n_scored_boundaries": pairs,
            }
        )
    scores = []
    for bucket in buckets:
        scores.append(float(sum(bucket) / len(bucket)) if bucket else 1.0)
    return scores, {"windows": windows_meta, "n_boundaries": len(scores)}


def duration(atoms: list[dict[str, Any]], start: int, end: int) -> float:
    return float(atoms[end]["end"]) - float(atoms[start]["start"])


def is_local_min(scores: list[float], index: int, lo: int, hi: int) -> bool:
    """Local minimum of the boundary after `index` within [lo, hi]."""
    if index < 0 or index >= len(scores):
        return False
    left = scores[index - 1] if index - 1 >= lo and index - 1 >= 0 else scores[index] + 1.0
    right = scores[index + 1] if index + 1 <= hi and index + 1 < len(scores) else scores[index] + 1.0
    return scores[index] <= left and scores[index] <= right


def select_chapters(
    atoms: list[dict[str, Any]],
    scores: list[float],
) -> tuple[list[list[int]], list[dict[str, Any]]]:
    n = len(atoms)
    start = 0
    runs: list[list[int]] = []
    ops: list[dict[str, Any]] = []
    while start < n:
        max_end = start
        for k in range(start, n):
            if duration(atoms, start, k) <= MAX_DURATION_SEC + 1e-12:
                max_end = k
            else:
                break
        if max_end == start and duration(atoms, start, start) > MAX_DURATION_SEC:
            run = list(range(atoms[start]["id"], atoms[start]["id"] + 1))
            runs.append(run)
            ops.append(
                make_op(
                    op="keep",
                    source_ids=run,
                    start=atoms[start]["start"],
                    end=atoms[start]["end"],
                    reason="unsplittable_over_max",
                )
            )
            start += 1
            continue
        if max_end == n - 1:
            run = [atom["id"] for atom in atoms[start:]]
            runs.append(run)
            ops.append(
                make_op(
                    op="keep" if start == 0 and max_end == n - 1 else "merge",
                    source_ids=run,
                    start=atoms[start]["start"],
                    end=atoms[-1]["end"],
                    reason="tail",
                )
            )
            break

        candidates: list[tuple[int, float, float, bool, bool]] = []
        for k in range(start, max_end + 1):
            dur = duration(atoms, start, k)
            if dur < MIN_CHAPTER_SEC and k < max_end:
                continue
            score = scores[k] if k < len(scores) else -1.0
            local = is_local_min(scores, k, start, max_end) if k < len(scores) else False
            preferred = PREF_MIN_SEC <= dur <= PREF_MAX_SEC
            candidates.append((k, dur, score, local, preferred))
        if not candidates:
            k = max_end
            candidates.append((k, duration(atoms, start, k), scores[k] if k < len(scores) else 1.0, False, False))

        pref_mins = [c for c in candidates if c[3] and c[4]]
        all_mins = [c for c in candidates if c[3] and c[1] >= MIN_CHAPTER_SEC]
        valid = [c for c in candidates if c[1] >= MIN_CHAPTER_SEC] or candidates
        pool = pref_mins or all_mins or valid
        cut_pool = [c for c in pool if c[0] < n - 1] or pool
        chosen = min(cut_pool, key=lambda item: (item[2], -item[1]))
        end = chosen[0]
        run = [atom["id"] for atom in atoms[start : end + 1]]
        runs.append(run)
        reason = "local_min" if chosen[3] else "deepest_in_max_window"
        if chosen[4]:
            reason = "preferred_local_min" if chosen[3] else "preferred_deepest"
        ops.append(
            make_op(
                op="merge" if len(run) > 1 else "keep",
                source_ids=run,
                start=atoms[start]["start"],
                end=atoms[end]["end"],
                reason=reason,
                extra={
                    "cosine": None if end >= len(scores) else round(float(scores[end]), 6),
                    "duration_sec": round(chosen[1], 3),
                    "local_min": chosen[3],
                    "preferred": chosen[4],
                },
            )
        )
        start = end + 1

    if len(runs) >= 2:
        last = runs[-1]
        last_atoms = [atom for atom in atoms if atom["id"] in last]
        last_dur = last_atoms[-1]["end"] - last_atoms[0]["start"]
        prev = runs[-2]
        prev_atoms = [atom for atom in atoms if atom["id"] in prev]
        combined = prev_atoms[-1]["end"] - prev_atoms[0]["start"] + 0  # placeholder
        combined = last_atoms[-1]["end"] - prev_atoms[0]["start"]
        if last_dur < MIN_CHAPTER_SEC and combined <= MAX_DURATION_SEC + 1e-12:
            merged = prev + last
            runs = runs[:-2] + [merged]
            ops.append(
                make_op(
                    op="merge",
                    source_ids=merged,
                    start=prev_atoms[0]["start"],
                    end=last_atoms[-1]["end"],
                    reason="absorb_short_tail",
                )
            )
    return runs, ops


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", default="cpu")
    args = parser.parse_args()
    leaves = attach_empty_asr(load_asr_leaves())
    expected = expected_ids(leaves)
    started = time.monotonic()
    try:
        tokenizer, model, loaded_model, load_note = load_jina(args.device)
    except RuntimeError as exc:
        payload = {
            "experiment": "D",
            "status": "skipped",
            "failure_kind": "install",
            "model": MODEL_ID,
            "error": str(exc),
            "alternatives_not_executed": ALTERNATIVES,
        }
        write_json(OUT_DIR / "exp_d_skipped.json", payload)
        print(json.dumps(payload, ensure_ascii=False))
        return

    scores, window_meta = collect_boundary_scores(leaves, tokenizer, model, args.device)
    runs, ops = select_chapters(leaves, scores)
    index = leaf_index(leaves)
    groups = [group_from_ids(run, index, title="") for run in runs]
    chapters = chapter_payload(groups, method="late_chunking", timing_source=TIMING_SOURCE_CD)
    validation = validate_chapters(chapters, leaves, timing_source=TIMING_SOURCE_CD)
    assert_valid(validation, "exp D")
    runtime = round(time.monotonic() - started, 3)
    log = write_merge_log(
        OUT_DIR / "merge_log_d.json",
        pass_no=8,
        method="late_chunking",
        input_artifact=TIMING_SOURCE_CD,
        timing_source=TIMING_SOURCE_CD,
        num_source=len(leaves),
        groups=groups,
        expected=expected,
        ops=ops,
        max_ids_per_group=None,
        extra={
            "experiment": "D",
            "embedding_model": loaded_model,
            "requested_model": MODEL_ID,
            "load_note": load_note,
            "window_sec": WINDOW_SEC,
            "overlap_sec": OVERLAP_SEC,
            "min_chapter_sec": MIN_CHAPTER_SEC,
            "preferred_chapter_sec": [PREF_MIN_SEC, PREF_MAX_SEC],
        },
    )
    write_json(OUT_DIR / "merge_log_pass8.json", log)
    write_json(OUT_DIR / "validation_d.json", validation)
    write_json(
        OUT_DIR / "exp_d_boundary_scores.json",
        {
            "experiment": "D",
            "embedding_model": loaded_model,
            "requested_model": MODEL_ID,
            "scores": [round(score, 6) for score in scores],
            "windows": window_meta,
        },
    )
    write_json(
        OUT_DIR / "exp_d_chapters.json",
        {
            "experiment": "D",
            "execution_mode": "local",
            "provider": "transformers",
            "embedding_model": loaded_model,
            "requested_model": MODEL_ID,
            "load_note": load_note,
            "input_artifact": TIMING_SOURCE_CD,
            "timing_source": TIMING_SOURCE_CD,
            "timing_method": "source_boundaries",
            "num_chapters": len(chapters),
            "runtime_sec": runtime,
            "alternatives_not_executed": ALTERNATIVES,
            "chapters": chapters,
            "validation": validation,
        },
    )
    write_json(
        OUT_DIR / "review_sheet_d.json",
        {"experiment": "D", "rows": review_sheet(chapters, "late_chunking")},
    )
    print(
        json.dumps(
            {
                "experiment": "D",
                "status": "success",
                "num_chapters": len(chapters),
                "runtime_sec": runtime,
                "n_windows": len(window_meta["windows"]),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

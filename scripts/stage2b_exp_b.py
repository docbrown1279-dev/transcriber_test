#!/usr/bin/env python3
"""Experiment B: pairwise Qwen3-8B same-topic decisions. Independent of A."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import argparse
import json
import re
import time
from pathlib import Path
from typing import Any

from llama_cpp import Llama

from stage2b_common import (
    LLM_DIR,
    MAX_DURATION_SEC,
    MAX_IDS_PER_GROUP_AB,
    OUT_DIR,
    TIMING_SOURCE_AB,
    assert_valid,
    caps_allow,
    chapter_payload,
    clip_title,
    expected_ids,
    group_from_ids,
    leaf_index,
    load_titled_leaves,
    make_op,
    merge_groups,
    review_sheet,
    validate_chapters,
    write_json,
    write_merge_log,
)

SYSTEM = (
    "Ты решаешь, относятся ли два соседних заголовка глав совещания к одной теме. "
    "Не пиши саммари встречи. Не придумывай время, id и факты. "
    "Можно склеивать только эту пару."
)
USER = (
    "/no_think\n"
    "Дана ровно одна соседняя пара. ids должны быть {left_id} и {right_id}.\n"
    "left_id={left_id} title={left_title}\n"
    "right_id={right_id} title={right_title}\n\n"
    "Ответь только JSON одной строки вида "
    '{{"ids":[{left_id},{right_id}],"same_topic":true,"title":"..."}} '
    "или same_topic false и title пустая строка \"\". "
    "Поле title всегда строка, не null и не без значения. "
    "Если same_topic true, title — новый заголовок не больше 10 русских слов "
    "только из двух старых названий. Другие id запрещены."
)
ID_RE = re.compile(r"-?\d+")


def parse_decision(raw: str, left_id: int, right_id: int) -> dict[str, Any]:
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I).strip()
    text = re.sub(r'"title"\s*:\s*(?=[,}])', '"title":""', text)
    text = text.replace(":}", ':""}').replace(":,", ':"",')
    start = text.find("{")
    end = text.rfind("}")
    parsed: dict[str, Any] | None = None
    if start >= 0 and end > start:
        try:
            value = json.loads(text[start : end + 1])
            if isinstance(value, dict):
                parsed = value
        except json.JSONDecodeError:
            parsed = None
    if parsed is None:
        return {
            "same_topic": False,
            "title": "",
            "ids_ok": False,
            "returned_ids": None,
            "reason": "unparseable",
        }
    returned = parsed.get("ids")
    ids_ok = False
    if isinstance(returned, list) and len(returned) == 2:
        try:
            ids_ok = [int(returned[0]), int(returned[1])] == [left_id, right_id]
        except (TypeError, ValueError):
            ids_ok = False
    same = parsed.get("same_topic")
    if isinstance(same, str):
        same = same.strip().lower() in {"true", "yes", "да", "1"}
    same = bool(same)
    title = clip_title(str(parsed.get("title") or ""))
    if not ids_ok:
        return {
            "same_topic": False,
            "title": "",
            "ids_ok": False,
            "returned_ids": returned,
            "reason": "ids_mismatch",
        }
    return {
        "same_topic": same,
        "title": title,
        "ids_ok": True,
        "returned_ids": [left_id, right_id],
        "reason": "same_topic" if same else "different_topic",
    }


def one_pass(
    groups: list[dict[str, Any]],
    llm: Llama,
    *,
    pass_no: int,
    calls: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if not groups:
        return [], []
    output: list[dict[str, Any]] = []
    current = dict(groups[0])
    ops: list[dict[str, Any]] = []
    cursor = 0
    for nxt in groups[1:]:
        left_id = cursor
        right_id = cursor + 1
        allowed, cap_reason = caps_allow(
            current, nxt, max_ids=MAX_IDS_PER_GROUP_AB, max_duration=MAX_DURATION_SEC
        )
        presented = [left_id, right_id]
        item_started = time.monotonic()
        if not allowed:
            decision = {
                "same_topic": False,
                "title": "",
                "ids_ok": True,
                "returned_ids": presented,
                "reason": cap_reason,
            }
            raw = ""
            runtime = 0.0
        else:
            response = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": USER.format(
                            left_id=left_id,
                            right_id=right_id,
                            left_title=current.get("title") or "",
                            right_title=nxt.get("title") or "",
                        ),
                    },
                ],
                max_tokens=80,
                temperature=0.1,
                top_p=0.9,
            )
            raw = (response["choices"][0]["message"]["content"] or "").strip()
            runtime = round(time.monotonic() - item_started, 3)
            decision = parse_decision(raw, left_id, right_id)
        call = {
            "pass": pass_no,
            "presented_ids": presented,
            "left_title": current.get("title") or "",
            "right_title": nxt.get("title") or "",
            "left_source_ids": list(current["source_ids"]),
            "right_source_ids": list(nxt["source_ids"]),
            "raw": raw,
            "decision": decision,
            "llm_runtime_sec": runtime,
            "caps_allowed": allowed,
        }
        calls.append(call)
        write_json(LLM_DIR / "exp_b_pair_decisions.json", {"calls": calls})
        if allowed and decision["same_topic"] and decision["ids_ok"]:
            title = decision["title"] or " | ".join(
                [current.get("title") or "", nxt.get("title") or ""]
            )
            merged = merge_groups(current, nxt, title)
            ops.append(
                make_op(
                    op="merge",
                    source_ids=list(merged["source_ids"]),
                    start=merged["start"],
                    end=merged["end"],
                    old_titles=[current.get("title") or "", nxt.get("title") or ""],
                    new_title=title,
                    reason="same_topic",
                    extra={"presented_ids": presented},
                )
            )
            current = merged
            # Stay on the merged chapter; next comparison uses the same left cursor.
            continue
        reason = decision["reason"]
        ops.append(
            make_op(
                op="keep",
                source_ids=list(current["source_ids"]),
                start=current["start"],
                end=current["end"],
                old_titles=[current.get("title") or ""],
                new_title=current.get("title") or "",
                reason=reason,
                extra={"presented_ids": presented},
            )
        )
        output.append(current)
        current = dict(nxt)
        cursor = len(output)
    output.append(current)
    return output, ops


def groups_from_leaves(leaves: list[dict[str, Any]]) -> list[dict[str, Any]]:
    index = leaf_index(leaves)
    return [group_from_ids([leaf["id"]], index, title=leaf.get("title") or "") for leaf in leaves]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--max-passes", type=int, default=2)
    args = parser.parse_args()

    leaves = load_titled_leaves()
    groups = groups_from_leaves(leaves)
    expected = expected_ids(leaves)
    started = time.monotonic()
    llm = Llama(
        model_path=str(args.model),
        n_ctx=4096,
        n_threads=args.threads,
        n_threads_batch=args.threads,
        n_batch=256,
        verbose=False,
    )
    calls: list[dict[str, Any]] = []
    pass_base = 4
    current = groups
    for pass_idx in range(1, args.max_passes + 1):
        current, ops = one_pass(current, llm, pass_no=pass_idx, calls=calls)
        chapters = chapter_payload(current, method="pairwise_llm", timing_source=TIMING_SOURCE_AB)
        validation = validate_chapters(chapters, leaves, timing_source=TIMING_SOURCE_AB)
        assert_valid(validation, f"exp B pass {pass_idx}")
        log = write_merge_log(
            OUT_DIR / f"merge_log_b_pass{pass_idx}.json",
            pass_no=pass_base + pass_idx - 1,
            method="pairwise_llm",
            input_artifact=TIMING_SOURCE_AB,
            timing_source=TIMING_SOURCE_AB,
            num_source=len(leaves),
            groups=current,
            expected=expected,
            ops=ops,
            max_ids_per_group=MAX_IDS_PER_GROUP_AB,
            extra={"experiment": "B", "llm_pass": pass_idx},
        )
        write_json(OUT_DIR / f"merge_log_pass{pass_base + pass_idx - 1}.json", log)
        write_json(OUT_DIR / f"validation_b_pass{pass_idx}.json", validation)
        write_json(
            OUT_DIR / f"exp_b_pass{pass_idx}.json",
            {
                "experiment": "B",
                "pass": pass_idx,
                "num_chapters": len(chapters),
                "chapters": chapters,
                "validation": validation,
            },
        )
        if not log["coverage_ok"]:
            raise RuntimeError(f"exp B pass {pass_idx} coverage failed")

    chapters = chapter_payload(current, method="pairwise_llm", timing_source=TIMING_SOURCE_AB)
    write_json(
        OUT_DIR / "exp_b_chapters.json",
        {
            "experiment": "B",
            "execution_mode": "local",
            "provider": "llama.cpp",
            "model": args.model.name,
            "input_artifact": TIMING_SOURCE_AB,
            "timing_source": TIMING_SOURCE_AB,
            "timing_method": "source_boundaries",
            "num_chapters": len(chapters),
            "llm_runtime_sec": round(time.monotonic() - started, 3),
            "n_pair_calls": sum(1 for call in calls if call["raw"]),
            "chapters": chapters,
        },
    )
    write_json(
        OUT_DIR / "review_sheet_b.json",
        {"experiment": "B", "rows": review_sheet(chapters, "pairwise_llm")},
    )
    write_json(
        LLM_DIR / "exp_b_pair_decisions.json",
        {
            "execution_mode": "local",
            "provider": "llama.cpp",
            "model": args.model.name,
            "input_artifact": TIMING_SOURCE_AB,
            "n_calls": len(calls),
            "calls": calls,
        },
    )
    print(
        json.dumps(
            {"experiment": "B", "num_chapters": len(chapters), "n_calls": len(calls)},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

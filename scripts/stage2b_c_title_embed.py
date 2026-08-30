#!/usr/bin/env python3
"""Optional C second pass: Experiment A title-embedding protocol on C titles."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import json

from sentence_transformers import SentenceTransformer

from stage2b_common import (
    OUT_DIR,
    TIMING_SOURCE_CD,
    assert_valid,
    chapter_payload,
    expected_ids,
    load_asr_leaves,
    review_sheet,
    validate_chapters,
    write_json,
    write_merge_log,
)
from stage2b_exp_c import title_embed_units


def main() -> None:
    payload = json.loads((OUT_DIR / "exp_c_chapters.json").read_text(encoding="utf-8"))
    chapters = payload["chapters"]
    if len(chapters) <= 20:
        print(json.dumps({"skipped": True, "reason": "already_<=20", "num_chapters": len(chapters)}))
        return
    if any(not (chapter.get("title") or "").strip() for chapter in chapters):
        raise RuntimeError("C title-embed requires titles on every chapter")
    groups = []
    for chapter in chapters:
        groups.append(
            {
                "source_ids": list(chapter.get("source_ids") or chapter["leaf_ids"]),
                "start_source_id": chapter.get("start_source_id"),
                "end_source_id": chapter.get("end_source_id"),
                "start": chapter["start"],
                "end": chapter["end"],
                "text": chapter.get("text") or "",
                "speakers": chapter.get("speakers") or [],
                "n_words": chapter.get("n_words") or 0,
                "title": chapter.get("title") or "",
                "old_titles": [chapter.get("title") or ""],
            }
        )
    model = SentenceTransformer("cointegrated/rubert-tiny2", device="cpu")
    selected = title_embed_units(groups, model)
    leaves = load_asr_leaves()
    remapped = selected["groups"]
    new_chapters = chapter_payload(
        remapped, method="pack_across_speakers", timing_source=TIMING_SOURCE_CD
    )
    validation = validate_chapters(new_chapters, leaves, timing_source=TIMING_SOURCE_CD)
    assert_valid(validation, "exp C title-embed")
    log = write_merge_log(
        OUT_DIR / "merge_log_c_title_embed.json",
        pass_no=7,
        method="title_embed_adjacent",
        input_artifact="results/chunking/2b/exp_c_chapters.json",
        timing_source=TIMING_SOURCE_CD,
        num_source=len(leaves),
        groups=remapped,
        expected=expected_ids(leaves),
        ops=selected["ops"],
        max_ids_per_group=8,
        extra={
            "experiment": "C",
            "stage": "title_embed",
            "threshold": selected["threshold"],
            "note": "max_ids_per_group applies to C-units, not raw ASR leaves",
        },
    )
    write_json(OUT_DIR / "merge_log_pass7.json", log)
    write_json(OUT_DIR / "validation_c_title_embed.json", validation)
    payload.update(
        {
            "title_embed_applied": True,
            "title_embed_threshold": selected["threshold"],
            "num_chapters": len(new_chapters),
            "chapters": new_chapters,
            "validation": validation,
        }
    )
    write_json(OUT_DIR / "exp_c_chapters.json", payload)
    write_json(
        OUT_DIR / "review_sheet_c.json",
        {"experiment": "C", "rows": review_sheet(new_chapters, "pack_across_speakers")},
    )
    print(
        json.dumps(
            {
                "title_embed_applied": True,
                "threshold": selected["threshold"],
                "num_chapters": len(new_chapters),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

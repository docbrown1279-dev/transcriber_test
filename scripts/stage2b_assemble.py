#!/usr/bin/env python3
"""Bundle A–D candidates into chapters.json without selecting a winner."""

from __future__ import annotations

import sys
from pathlib import Path as _Path
sys.path.insert(0, str(_Path(__file__).resolve().parent))

import json
from pathlib import Path

from stage2b_common import OUT_DIR, write_json


def slim(chapter: dict) -> dict:
    return {
        "id": chapter["id"],
        "start": chapter["start"],
        "end": chapter["end"],
        "title": chapter.get("title") or "",
        "leaf_ids": list(chapter.get("leaf_ids") or chapter.get("source_ids") or []),
        "speakers": list(chapter.get("speakers") or []),
        "n_words": chapter.get("n_words"),
        "text": chapter.get("text") or "",
    }


def load_candidate(name: str, path: Path) -> dict | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("status") == "skipped":
        return payload
    chapters = [slim(row) for row in payload.get("chapters") or []]
    return {
        "experiment": name,
        "num_chapters": len(chapters),
        "artifact": str(path.relative_to(path.parents[2]) if False else path.as_posix()),
        "method": (payload.get("chapters") or [{}])[0].get("method") if chapters else None,
        "chapters": chapters,
    }


def main() -> None:
    candidates = {
        "A": load_candidate("A", OUT_DIR / "exp_a_chapters.json"),
        "B": load_candidate("B", OUT_DIR / "exp_b_chapters.json"),
        "C": load_candidate("C", OUT_DIR / "exp_c_chapters.json"),
        "D": load_candidate("D", OUT_DIR / "exp_d_chapters.json")
        or load_candidate("D", OUT_DIR / "exp_d_skipped.json"),
    }
    write_json(
        OUT_DIR / "chapters.json",
        {
            "stage": "2b",
            "winner_selected": False,
            "note": "Четыре независимых кандидата. Победителя без человеческой оценки не выбираем.",
            "candidates": candidates,
        },
    )
    print(
        json.dumps(
            {
                name: None if row is None else row.get("num_chapters") or row.get("status")
                for name, row in candidates.items()
            }
        )
    )


if __name__ == "__main__":
    main()

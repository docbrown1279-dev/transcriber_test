#!/usr/bin/env python3
"""Run part1 TTFT spike: diarize+ASR+packing C (no LLM titles).

Forces ``pipeline.toc_mode=a`` for this process only so ``--until chunk`` does not
enter streaming titles (mode b). Does not modify on-disk product configs.

Records wall times; ``ttft_first_chapter_sec`` = time until chapters.json exists
after job start. Report also lists ``ttft_plus_llm_budget_sec`` (= TTFT + 2.0).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

from transcriber.config.loader import load_config
from transcriber.pipeline.orchestrator import run_job


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--audio", type=Path, required=True)
    ap.add_argument("--job-dir", type=Path, required=True)
    ap.add_argument("--profile", default="demo")
    ap.add_argument("--onnx-threads", type=int, default=2)
    ap.add_argument("--llm-budget-sec", type=float, default=2.0)
    ap.add_argument("--out-timing", type=Path, required=True)
    args = ap.parse_args()

    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    cfg = load_config(profile=args.profile)
    cfg = cfg.model_copy(deep=True)
    cfg.pipeline.toc_mode = "a"
    cfg.vad.onnx_threads = args.onnx_threads
    cfg.diarization.onnx_threads = args.onnx_threads
    # Keep short clusters: do not raise absorb / do not filter speaker ids.
    # cluster_distance_threshold stays at profile/base (0.85).

    args.job_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    marks: dict[str, float] = {"start": 0.0}

    def on_event(ev: object) -> None:
        stage = getattr(ev, "stage", None)
        status = getattr(ev, "status", None)
        if stage and status == "done":
            marks[f"{stage}_done"] = round(time.monotonic() - t0, 3)

    run_job(
        job_dir=args.job_dir,
        source_audio=args.audio,
        until="chunk",
        cfg=cfg,
        events=on_event,
    )
    total = round(time.monotonic() - t0, 3)
    chapters_path = args.job_dir / "chapters.json"
    ttft = marks.get("chunk_done", total if chapters_path.is_file() else None)

    turns = {}
    turns_path = args.job_dir / "turns.json"
    if turns_path.is_file():
        turns = json.loads(turns_path.read_text(encoding="utf-8"))

    chapters = {}
    if chapters_path.is_file():
        chapters = json.loads(chapters_path.read_text(encoding="utf-8"))

    timing = {
        "schema_version": "1",
        "audio": str(args.audio),
        "job_dir": str(args.job_dir),
        "profile": args.profile,
        "toc_mode_forced": "a",
        "until": "chunk",
        "onnx_threads": args.onnx_threads,
        "cluster_distance_threshold": cfg.diarization.embed.cluster_distance_threshold,
        "marks_sec": marks,
        "wall_total_sec": total,
        "ttft_first_chapter_sec": ttft,
        "ttft_plus_llm_budget_sec": (
            round(ttft + args.llm_budget_sec, 3) if ttft is not None else None
        ),
        "llm_budget_sec": args.llm_budget_sec,
        "speaker_count": turns.get("speaker_count"),
        "n_turns": len(turns.get("turns") or []),
        "n_chapters": len(chapters.get("chapters") or []),
        "gate_hint_sec": 300,
        "notes": [
            "No LLM titles in this spike; +llm_budget approximates first titled chapter.",
            "Short clusters kept (no post-filter of speaker ids).",
        ],
    }
    args.out_timing.parent.mkdir(parents=True, exist_ok=True)
    args.out_timing.write_text(
        json.dumps(timing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(timing, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

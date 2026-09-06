#!/usr/bin/env python3
"""D4.1 A/B bench: batch titles (A) vs ASR-slice pipeline (B)."""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import monotonic

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from transcriber.config.loader import load_config
from transcriber.llm.factory import make_client
from transcriber.llm.titles import apply_titles_batch
from transcriber.models.artifacts import ChaptersArtifact, TranscriptArtifact, load_artifact, dump_artifact
from transcriber.pipeline.pipeline_b import run_pipeline_b


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bench_d4_1")


def _rss_mb() -> float:
    return round(getrusage(RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def run_mode_a(job_dir: Path, profile: str | None) -> dict:
    """Batch titles on existing transcript+chapters (strip titles first)."""
    cfg = load_config(profile)
    cfg.llm.titles_mode = "batch"
    transcript = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
    chapters = load_artifact(job_dir / "chapters.json", ChaptersArtifact)
    cleared = chapters.model_copy(deep=True)
    for ch in cleared.chapters:
        ch.title = ""
    client = make_client(cfg.llm)
    t0 = monotonic()
    titled, calls = apply_titles_batch(cleared, transcript, client, cfg.llm)
    wall = round(monotonic() - t0, 3)
    dump_artifact(titled, job_dir / "chapters.json")
    return {
        "mode": "a",
        "titles_llm_calls": calls,
        "titles_wall_sec": wall,
        "time_to_first_titled_chapter_sec": wall,  # batch returns all at once
        "time_to_all_titles_sec": wall,
        "chapters": len(titled.chapters),
        "titles": [c.title for c in titled.chapters],
        "peak_rss_mb": _rss_mb(),
        "notes": "titles-only on existing transcript/chapters; speech stages not re-run",
    }


def run_mode_b(job_dir: Path, profile: str | None) -> dict:
    """Full ASR→glue→async titles from turns (in-process GigaAM)."""
    cfg = load_config(profile)
    # Force sequential single-chapter prompt for B
    cfg.llm.titles_mode = "sequential"
    t0 = monotonic()
    _transcript, chapters, stats = run_pipeline_b(job_dir, cfg)
    total = round(monotonic() - t0, 3)
    return {
        "mode": "b",
        "titles_llm_calls": stats.titles_llm_calls,
        "asr_wall_sec": stats.asr_wall_sec,
        "glue_wall_sec": stats.glue_wall_sec,
        "time_to_first_titled_chapter_sec": stats.time_to_first_titled_chapter_sec,
        "time_to_all_titles_sec": stats.time_to_all_titles_sec,
        "total_wall_sec": total,
        "chapters": len(chapters.chapters),
        "titles": [c.title for c in chapters.chapters],
        "peak_rss_mb": stats.peak_rss_mb,
        "notes": "; ".join(stats.notes),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("a", "b"), required=True)
    parser.add_argument("--job", type=Path, required=True, help="Job directory")
    parser.add_argument("--profile", default="demo")
    parser.add_argument("--out", type=Path, required=True, help="Report JSON path")
    parser.add_argument(
        "--seed-from",
        type=Path,
        default=None,
        help="Copy normalize/vad/diar artifacts from this job (mode b)",
    )
    args = parser.parse_args()

    job = args.job
    job.mkdir(parents=True, exist_ok=True)

    if args.mode == "b" and args.seed_from is not None:
        seed = args.seed_from
        for name in ("audio.json", "speech.json", "turns.json", "normalized.wav", "vad_input.wav"):
            src = seed / name
            if not src.exists():
                raise SystemExit(f"missing seed artifact: {src}")
            dest = job / name
            if src.is_file():
                shutil.copy2(src, dest)
        for stale in ("transcript.json", "chapters.json", "suggestions.json"):
            p = job / stale
            if p.exists():
                p.unlink()

    if args.mode == "a":
        report = run_mode_a(job, args.profile)
    else:
        report = run_mode_b(job, args.profile)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("wrote %s", args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

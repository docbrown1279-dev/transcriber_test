#!/usr/bin/env python3
"""D5 G5 bench: full pipeline under Docker cgroup limits.

Accepts ``--audio`` (host/container path), ``--mode a|b``, ``--out`` JSON.
Reuses orchestrator ``run_job`` (same toc_mode A/B behaviour as the web demo).
For titles-only A/B on a seeded job dir, prefer ``scripts/bench_d4_1.py``.

Records ``ttft_first_chapter_sec`` (job start → first schema-valid chapters.json).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
import threading
import time
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import monotonic
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from transcriber.config.loader import load_config  # noqa: E402
from transcriber.models.artifacts import (  # noqa: E402
    AudioArtifact,
    ChaptersArtifact,
    SpeechArtifact,
    TranscriptArtifact,
    TurnsArtifact,
    load_artifact,
)
from transcriber.pipeline.orchestrator import run_job  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("bench_d5")


def _rss_mb() -> float:
    return round(getrusage(RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def _safe_runtime(path: Path, model: type[Any]) -> float | None:
    if not path.is_file():
        return None
    try:
        art = load_artifact(path, model)
    except Exception as exc:
        logger.warning("could not read %s: %s", path, exc)
        return None
    value = getattr(art, "runtime_sec", None)
    return float(value) if value is not None else None


def _collect_stages(job_dir: Path) -> list[dict[str, Any]]:
    mapping: list[tuple[str, Path, type[Any]]] = [
        ("normalize", job_dir / "audio.json", AudioArtifact),
        ("vad", job_dir / "speech.json", SpeechArtifact),
        ("diarize", job_dir / "turns.json", TurnsArtifact),
        ("asr", job_dir / "transcript.json", TranscriptArtifact),
        ("chunk", job_dir / "chapters.json", ChaptersArtifact),
        ("titles", job_dir / "chapters.json", ChaptersArtifact),
    ]
    stages: list[dict[str, Any]] = []
    for name, path, model in mapping:
        stages.append(
            {
                "stage": name,
                "wall_sec": _safe_runtime(path, model),
                "peak_rss_mb": None,
            }
        )
    return stages


def _watch_first_chapters(job_dir: Path, t0: float, holder: dict[str, Any]) -> None:
    """Poll for first schema-valid chapters.json (TTFT clock)."""
    path = job_dir / "chapters.json"
    while holder.get("stop") is not True:
        if path.is_file():
            try:
                load_artifact(path, ChaptersArtifact)
                holder["ttft_first_chapter_sec"] = round(monotonic() - t0, 3)
                return
            except Exception:
                pass
        time.sleep(0.25)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", type=Path, required=True, help="Input media path")
    parser.add_argument("--mode", choices=("a", "b"), required=True)
    parser.add_argument("--out", type=Path, required=True, help="Report JSON path")
    parser.add_argument(
        "--job-dir",
        type=Path,
        default=None,
        help="Job working directory (default: under TRANSCRIBER_STORAGE_ROOT or ./var/bench/d5)",
    )
    parser.add_argument("--profile", default="demo")
    parser.add_argument(
        "--until",
        default="titles",
        help="Pipeline until stage (default: titles)",
    )
    args = parser.parse_args()

    audio = args.audio.expanduser().resolve()
    if not audio.is_file():
        raise SystemExit(f"audio not found: {audio}")

    cfg = load_config(args.profile)
    cfg = cfg.model_copy(deep=True)
    cfg.pipeline.toc_mode = args.mode
    if args.mode == "a":
        cfg.llm.titles_mode = "batch"

    if args.job_dir is not None:
        job_dir = args.job_dir.expanduser().resolve()
    else:
        job_dir = Path(cfg.app.storage_root).resolve() / "bench" / "d5" / f"job_mode_{args.mode}"
    job_dir.mkdir(parents=True, exist_ok=True)

    dest = job_dir / f"upload{audio.suffix.lower() or '.m4a'}"
    if dest.resolve() != audio:
        shutil.copy2(audio, dest)
    logger.info(
        "job_dir=%s audio=%s mode=%s ttft_split=%s",
        job_dir,
        dest,
        args.mode,
        cfg.pipeline.ttft_split,
    )

    t0 = monotonic()
    peak_before = _rss_mb()
    ttft_holder: dict[str, Any] = {"ttft_first_chapter_sec": None, "stop": False}
    watcher = threading.Thread(
        target=_watch_first_chapters,
        args=(job_dir, t0, ttft_holder),
        daemon=True,
    )
    watcher.start()
    try:
        run_job(job_dir=job_dir, source_audio=dest, until=args.until, cfg=cfg)
    finally:
        ttft_holder["stop"] = True
        watcher.join(timeout=2.0)
    total_wall = round(monotonic() - t0, 3)
    peak_rss = max(peak_before, _rss_mb())

    ttft_sec = ttft_holder.get("ttft_first_chapter_sec")
    mark_path = job_dir / "ttft_mark.json"
    if mark_path.is_file():
        try:
            mark = json.loads(mark_path.read_text(encoding="utf-8"))
            if mark.get("ttft_first_chapter_sec") is not None:
                ttft_sec = float(mark["ttft_first_chapter_sec"])
        except Exception as exc:
            logger.warning("ttft_mark read failed: %s", exc)

    chapters: list[str] = []
    chapters_path = job_dir / "chapters.json"
    if chapters_path.is_file():
        try:
            ch = load_artifact(chapters_path, ChaptersArtifact)
            chapters = [c.title for c in ch.chapters]
        except Exception as exc:
            logger.warning("chapters read failed: %s", exc)

    report: dict[str, Any] = {
        "mode": args.mode,
        "audio": str(audio),
        "job_dir": str(job_dir),
        "until": args.until,
        "ttft_split": bool(cfg.pipeline.ttft_split),
        "ttft_first_chapter_sec": ttft_sec,
        "total_wall_sec": total_wall,
        "peak_rss_mb": peak_rss,
        "stages": _collect_stages(job_dir),
        "chapters": len(chapters),
        "titles": chapters,
        "notes": (
            "full run_job from audio; ttft_first_chapter_sec = job start → first valid "
            "chapters.json; stage wall_sec from artifact runtime_sec where present; "
            "peak_rss_mb is process RUSAGE_SELF after run"
        ),
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("wrote %s", args.out)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

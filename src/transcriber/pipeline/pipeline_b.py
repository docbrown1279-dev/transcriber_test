"""Mode B: ASR slice → incremental packing C → async chapter titles.

Title policy: fire LLM only when the *next* chapter appears (previous is closed).
Last chapter is titled at EOS. One title per closed slot — no re-fire on fingerprint growth.
"""

from __future__ import annotations

import logging
import os
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from resource import RUSAGE_SELF, getrusage
from time import monotonic
from typing import Any

from transcriber.asr.gigaam import transcribe_slices_with_model
from transcriber.chunking.packing_c import (
    absorb_short_units,
    merge_similar_units,
    pack_speaker_pieces,
)
from transcriber.config.schema import AppConfig
from transcriber.llm.factory import make_client
from transcriber.llm.titles import title_one_chapter
from transcriber.models.artifacts import (
    AudioArtifact,
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    TranscriptArtifact,
    TranscriptSegment,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)
from transcriber.registry import build

logger = logging.getLogger(__name__)


def _peak_rss_mb() -> float:
    return round(getrusage(RUSAGE_SELF).ru_maxrss / 1024.0, 1)


def _buffer_to_chapters(
    segments: list[TranscriptSegment],
    embedder: Any,
    cfg: AppConfig,
    *,
    apply_absorb: bool,
) -> list[ChapterItem]:
    if not segments:
        return []
    units = pack_speaker_pieces(segments, cfg.chunking)
    non_empty = [unit for unit in units if unit.text]
    if not non_empty:
        return []
    vectors = embedder.encode([unit.text for unit in non_empty])
    merged = merge_similar_units(non_empty, vectors, cfg.chunking)
    if apply_absorb:
        merged = absorb_short_units(merged, cfg.chunking)
    out: list[ChapterItem] = []
    for index, unit in enumerate(merged):
        speakers = list(dict.fromkeys(segment.speaker for segment in unit.segments))
        out.append(
            ChapterItem(
                id=f"C{index:02d}",
                start=unit.start,
                end=unit.end,
                source_ids=[segment.id for segment in unit.segments],
                speakers=speakers,
                title="",
                duration_sec=round(unit.duration, 3),
            )
        )
    return out


@dataclass
class PipelineBStats:
    """Timing counters for mode-B bench reports."""

    asr_wall_sec: float = 0.0
    glue_wall_sec: float = 0.0
    titles_llm_calls: int = 0
    time_to_first_titled_chapter_sec: float | None = None
    time_to_all_titles_sec: float | None = None
    peak_rss_mb: float = 0.0
    notes: list[str] = field(default_factory=list)


def run_pipeline_b(
    job_dir: Path,
    cfg: AppConfig,
    *,
    max_workers: int = 4,
) -> tuple[TranscriptArtifact, ChaptersArtifact, PipelineBStats]:
    """ASR→glue→async titles; requires audio.json + turns.json + normalized.wav."""
    job_dir = Path(job_dir)
    t_run0 = monotonic()
    stats = PipelineBStats()
    stats.notes.append("title only when next chapter appears; last at EOS")

    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

    turns = load_artifact(job_dir / "turns.json", TurnsArtifact)
    audio_art = load_artifact(job_dir / "audio.json", AudioArtifact)
    wav_path = job_dir / "normalized.wav"
    if not wav_path.is_file():
        raise FileNotFoundError(str(wav_path))

    embedder = build("embeddings", cfg.chunking.embedding_model, cfg.app.profile)
    client = make_client(cfg.llm)

    segments: list[TranscriptSegment] = []
    # Slot index -> chapter snapshot / title result (one LLM per slot)
    closed_items: dict[int, ChapterItem] = {}
    pending: dict[int, Future[tuple[str, int]]] = {}
    n_closed_titled = 0
    calls = 0
    glue_acc = 0.0

    def _snapshot_transcript() -> TranscriptArtifact:
        return TranscriptArtifact(
            schema_version="1",
            job_id=turns.job_id,
            engine="gigaam_v3_rnnt",
            language="ru",
            segments=list(segments),
            holes=list(turns.holes),
            max_segment_sec=cfg.asr.max_segment_seconds,
            runtime_sec=0.0,
        )

    def _title_work(chapter: ChapterItem) -> tuple[str, int]:
        return title_one_chapter(
            chapter,
            _snapshot_transcript(),
            client,
            cfg.llm,
            used_titles=None,
            calls_so_far=0,
        )

    def _drain_done() -> None:
        nonlocal calls
        done_slots = [slot for slot, fut in pending.items() if fut.done()]
        for slot in done_slots:
            fut = pending.pop(slot)
            try:
                title, used = fut.result()
            except Exception as exc:
                logger.warning("pipeline_b title failed slot=%s err=%s", slot, exc)
                stats.notes.append(f"title_fail_slot_{slot}:{exc}")
                continue
            calls += used
            if slot in closed_items:
                closed_items[slot].title = title
            if stats.time_to_first_titled_chapter_sec is None:
                stats.time_to_first_titled_chapter_sec = round(monotonic() - t_run0, 3)
            cid = closed_items[slot].id if slot in closed_items else "?"
            logger.info("pipeline_b titled slot=%s id=%s title=%s", slot, cid, title)

    def _close_through(chapters: list[ChapterItem], pool: ThreadPoolExecutor) -> None:
        """Title slots 0..len(chapters)-2 once each — closed because a newer chapter exists."""
        nonlocal n_closed_titled
        n_closed = max(0, len(chapters) - 1)
        while n_closed_titled < n_closed:
            slot = n_closed_titled
            chapter = chapters[slot].model_copy(deep=True)
            closed_items[slot] = chapter
            pending[slot] = pool.submit(_title_work, chapter)
            n_closed_titled += 1
            logger.info(
                "pipeline_b close slot=%s id=%s dur=%.1f (next chapter appeared)",
                slot,
                chapter.id,
                chapter.duration_sec,
            )

    with ThreadPoolExecutor(max_workers=max_workers) as pool:

        def on_segment(segment: TranscriptSegment) -> None:
            nonlocal glue_acc
            t0 = monotonic()
            segments.append(segment)
            chapters = _buffer_to_chapters(segments, embedder, cfg, apply_absorb=False)
            _close_through(chapters, pool)
            _drain_done()
            glue_acc += monotonic() - t0
            stats.peak_rss_mb = max(stats.peak_rss_mb, _peak_rss_mb())

        t_asr0 = monotonic()
        transcript = transcribe_slices_with_model(
            wav_path=wav_path,
            turns=turns,
            max_segment_sec=cfg.asr.max_segment_seconds,
            gain_db=float(audio_art.loudness.gain_db),
            per_turn_gain=bool(audio_art.asr_per_turn_gain),
            job_id=turns.job_id or job_dir.name,
            on_segment=on_segment,
        )
        asr_total = monotonic() - t_asr0
        stats.asr_wall_sec = round(asr_total - glue_acc, 3)

        t_eos = monotonic()
        final_chapters = _buffer_to_chapters(segments, embedder, cfg, apply_absorb=True)
        # EOS: title any slot not yet closed (including the last open chapter)
        for slot, chapter in enumerate(final_chapters):
            if slot in closed_items or slot in pending:
                # Keep existing title; refresh bounds from final chapter at assemble time
                continue
            item = chapter.model_copy(deep=True)
            closed_items[slot] = item
            pending[slot] = pool.submit(_title_work, item)
            logger.info("pipeline_b EOS title slot=%s id=%s", slot, chapter.id)
        glue_acc += monotonic() - t_eos
        stats.glue_wall_sec = round(glue_acc, 3)

        for slot, fut in list(pending.items()):
            try:
                title, used = fut.result()
            except Exception as exc:
                logger.warning("pipeline_b title failed at EOS slot=%s err=%s", slot, exc)
                title, used = title_one_chapter(
                    closed_items[slot],
                    _snapshot_transcript(),
                    client,
                    cfg.llm,
                    used_titles=None,
                    calls_so_far=calls,
                )
            calls += used
            closed_items[slot].title = title
            if stats.time_to_first_titled_chapter_sec is None:
                stats.time_to_first_titled_chapter_sec = round(monotonic() - t_run0, 3)
        pending.clear()

        # Local uniqueness (should be rare with one-shot-per-slot)
        seen: set[str] = set()
        for slot in sorted(closed_items):
            item = closed_items[slot]
            base = " ".join(item.title.split()) or "Глава"
            title = base
            n = 2
            while title.casefold() in seen:
                title = f"{base} ({n})"
                n += 1
                if n > 20:
                    break
            item.title = title
            seen.add(title.casefold())

        stats.titles_llm_calls = calls
        stats.time_to_all_titles_sec = round(monotonic() - t_run0, 3)
        stats.peak_rss_mb = max(stats.peak_rss_mb, _peak_rss_mb())

        # Final TOC: prefer final_chapters bounds; titles by slot index
        ordered: list[ChapterItem] = []
        for index, chapter in enumerate(final_chapters):
            titled = closed_items.get(index)
            if titled is None or not titled.title.strip():
                raise RuntimeError(f"Missing title for chapter slot {index}")
            ordered.append(
                chapter.model_copy(
                    update={
                        "id": f"C{index:02d}",
                        "title": titled.title,
                    }
                )
            )

        # Stream may have closed more slots than absorb kept; note wasted calls.
        if len(closed_items) > len(final_chapters):
            stats.notes.append(
                f"stream_closed_slots={len(closed_items)} final_chapters={len(final_chapters)}"
            )

    meeting_minutes = max(seg.end for seg in segments) / 60.0 if segments else 0.0
    short_limit, long_limit = cfg.chunking.target_chapter_sec
    chapters_art = ChaptersArtifact(
        schema_version="1",
        job_id=transcript.job_id,
        chunker="packing_c",
        embedding_model=embedder.name,
        similarity_threshold=cfg.chunking.similarity_threshold,
        chapters=ordered,
        metrics=ChapterMetrics(
            chapters_per_minute=round(len(ordered) / meeting_minutes, 3)
            if meeting_minutes
            else 0.0,
            short_chapters=sum(c.duration_sec < short_limit for c in ordered),
            long_chapters=sum(c.duration_sec > long_limit for c in ordered),
        ),
        runtime_sec=round(stats.glue_wall_sec, 3),
    )
    dump_artifact(transcript, job_dir / "transcript.json")
    dump_artifact(chapters_art, job_dir / "chapters.json")
    return transcript, chapters_art, stats

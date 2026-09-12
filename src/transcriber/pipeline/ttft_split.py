"""TTFT file-split pipeline: one normalize+VAD, pause parts, method B mid, V1 EOS."""

from __future__ import annotations

import json
import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from time import monotonic
from typing import Any

import numpy as np
import soundfile as sf

from transcriber.asr.gigaam import transcribe_slices_with_model
from transcriber.asr.holes import find_holes
from transcriber.audio.normalize import FfmpegAudioNormalizer
from transcriber.chunking.packing_c import (
    absorb_short_units,
    merge_similar_units,
    pack_speaker_pieces,
)
from transcriber.config.schema import AppConfig
from transcriber.diarization.eos_refine import refine_window_speakers_v1
from transcriber.diarization.gallery import SpeakerGallery, ahc_labels
from transcriber.diarization.wespeaker import (
    WeSpeakerDiarizer,
    extract_wespeaker_windows,
    turns_from_window_speakers,
    window_speakers_after_turns,
)
from transcriber.llm.factory import make_client
from transcriber.llm.titles import title_one_chapter
from transcriber.models.artifacts import (
    AudioArtifact,
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    SpeechArtifact,
    TimeInterval,
    TranscriptArtifact,
    TranscriptSegment,
    TurnItem,
    TurnMergeInfo,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)
from transcriber.pipeline.events import StageEvent
from transcriber.pipeline.pause_cut import plan, propose_n_parts
from transcriber.registry import build

logger = logging.getLogger(__name__)

EventSink = Callable[[StageEvent], None]
WINDOWS_NPZ = "ttft_windows.npz"
CENTROIDS_JSON = "centroids.json"
CUT_PLAN_JSON = "cut_plan.json"
TTFT_MARK_JSON = "ttft_mark.json"


def should_run_ttft_split(cfg: AppConfig, duration_sec: float) -> bool:
    """True when flag on and file is long enough for at least two parts."""
    if not cfg.pipeline.ttft_split:
        return False
    return duration_sec >= 2.0 * cfg.pipeline.ttft.min_part_sec


def _emit(events: EventSink | None, event: StageEvent) -> None:
    if events is not None:
        events(event)


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _patch_job_flags(
    job_dir: Path,
    *,
    early_ready: bool | None = None,
    speakers_finalized: bool | None = None,
) -> None:
    path = job_dir / "job.json"
    if not path.is_file():
        return
    from transcriber.models.artifacts import JobArtifact

    job = load_artifact(path, JobArtifact)
    updates: dict[str, Any] = {}
    if early_ready is not None:
        updates["early_ready"] = early_ready
    if speakers_finalized is not None:
        updates["speakers_finalized"] = speakers_finalized
    if not updates:
        return
    dump_artifact(job.model_copy(update=updates), path.with_name("job.json.tmp"))
    path.with_name("job.json.tmp").replace(path)


def _slice_wav(src: Path, dest: Path, start: float, end: float) -> None:
    """Time-slice already-normalized wav (no second gain)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    duration = max(0.0, end - start)
    cmd = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-ss",
        f"{start:.3f}",
        "-i",
        str(src),
        "-t",
        f"{duration:.3f}",
        "-c",
        "copy",
        str(dest),
    ]
    subprocess.run(cmd, check=True)


def _speech_for_part(
    speech: SpeechArtifact,
    *,
    part_start: float,
    part_end: float,
    job_id: str,
) -> SpeechArtifact:
    """Clip speech regions to part and shift to part-local time (for diarize on slice)."""
    regions: list[TimeInterval] = []
    for region in speech.regions:
        a = max(region.start, part_start)
        b = min(region.end, part_end)
        if b > a + 1e-6:
            regions.append(
                TimeInterval(start=round(a - part_start, 3), end=round(b - part_start, 3))
            )
    speech_sec = round(sum(r.end - r.start for r in regions), 3)
    return SpeechArtifact(
        schema_version="1",
        job_id=job_id,
        detector=speech.detector,
        fallback_used=speech.fallback_used,
        regions=regions,
        fallback_regions=[],
        speech_sec=speech_sec,
        runtime_sec=0.0,
    )


def _shift_turns_abs(
    turns: TurnsArtifact,
    offset: float,
    *,
    job_id: str,
    total_duration: float,
    min_hole_sec: float,
) -> TurnsArtifact:
    shifted = [
        TurnItem(
            id=t.id,
            start=round(t.start + offset, 3),
            end=round(t.end + offset, 3),
            speaker=t.speaker,
        )
        for t in turns.turns
    ]
    return turns.model_copy(
        update={
            "job_id": job_id,
            "turns": shifted,
            "holes": find_holes(shifted, total_duration, min_hole_sec=min_hole_sec),
            "speaker_count": len({t.speaker for t in shifted}),
        }
    )


def _shift_segments(
    segments: list[TranscriptSegment],
    offset: float,
    *,
    id_prefix: str,
) -> list[TranscriptSegment]:
    out: list[TranscriptSegment] = []
    for seg in segments:
        out.append(
            seg.model_copy(
                update={
                    "id": f"{id_prefix}:{seg.id}",
                    "start": round(seg.start + offset, 3),
                    "end": round(seg.end + offset, 3),
                }
            )
        )
    return out


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


def _write_chapters(
    job_dir: Path,
    job_id: str,
    chapters: list[ChapterItem],
    cfg: AppConfig,
    embedder: Any,
    *,
    runtime_sec: float,
) -> ChaptersArtifact:
    meeting_minutes = max((c.end for c in chapters), default=0.0) / 60.0
    short_limit, long_limit = cfg.chunking.target_chapter_sec
    art = ChaptersArtifact(
        schema_version="1",
        job_id=job_id,
        chunker="packing_c",
        embedding_model=getattr(embedder, "name", cfg.chunking.embedding_model),
        similarity_threshold=cfg.chunking.similarity_threshold,
        chapters=chapters,
        metrics=ChapterMetrics(
            chapters_per_minute=round(len(chapters) / meeting_minutes, 3)
            if meeting_minutes
            else 0.0,
            short_chapters=sum(c.duration_sec < short_limit for c in chapters),
            long_chapters=sum(c.duration_sec > long_limit for c in chapters),
        ),
        runtime_sec=round(runtime_sec, 3),
    )
    dump_artifact(art, job_dir / "chapters.json")
    return art


def _append_windows(
    job_dir: Path,
    abs_segments: list[tuple[float, float]],
    embeddings: np.ndarray,
    mid_speakers: list[str],
) -> None:
    path = job_dir / WINDOWS_NPZ
    if path.is_file():
        prev = np.load(path, allow_pickle=True)
        starts = np.concatenate([prev["starts"], np.asarray([s for s, _ in abs_segments])])
        ends = np.concatenate([prev["ends"], np.asarray([e for _, e in abs_segments])])
        embs = np.concatenate([prev["embeddings"], embeddings], axis=0)
        mids = list(prev["mid_speakers"].tolist()) + mid_speakers
    else:
        starts = np.asarray([s for s, _ in abs_segments], dtype=np.float64)
        ends = np.asarray([e for _, e in abs_segments], dtype=np.float64)
        embs = embeddings
        mids = mid_speakers
    np.savez_compressed(
        path,
        starts=starts,
        ends=ends,
        embeddings=embs,
        mid_speakers=np.asarray(mids, dtype=object),
    )


def _load_windows(
    job_dir: Path,
) -> tuple[list[tuple[float, float]], np.ndarray, list[str]]:
    path = job_dir / WINDOWS_NPZ
    if not path.is_file():
        return [], np.zeros((0, 0), dtype=np.float64), []
    data = np.load(path, allow_pickle=True)
    segments = list(zip(data["starts"].tolist(), data["ends"].tolist(), strict=True))
    mids = [str(x) for x in data["mid_speakers"].tolist()]
    return segments, data["embeddings"], mids


def _speaker_at(turns: list[TurnItem], t: float) -> str | None:
    for turn in turns:
        if turn.start - 1e-6 <= t <= turn.end + 1e-6:
            return turn.speaker
    return None


def _apply_speaker_map_to_transcript(
    transcript: TranscriptArtifact,
    turns: list[TurnItem],
) -> TranscriptArtifact:
    segs: list[TranscriptSegment] = []
    for seg in transcript.segments:
        mid = (seg.start + seg.end) / 2.0
        spk = _speaker_at(turns, mid) or seg.speaker
        segs.append(seg.model_copy(update={"speaker": spk}))
    return transcript.model_copy(update={"segments": segs})


def _rewrite_chapter_speakers(
    chapters: list[ChapterItem],
    transcript: TranscriptArtifact,
) -> list[ChapterItem]:
    by_id = {s.id: s for s in transcript.segments}
    out: list[ChapterItem] = []
    for ch in chapters:
        speakers = list(
            dict.fromkeys(by_id[sid].speaker for sid in ch.source_ids if sid in by_id)
        )
        out.append(ch.model_copy(update={"speakers": speakers}))
    return out


def run_ttft_split(
    job_dir: Path | str,
    cfg: AppConfig,
    *,
    source_audio: Path | str | None = None,
    events: EventSink | None = None,
    until: str = "titles",
) -> dict[str, Path]:
    """Full TTFT path: normalize+VAD once → parts → early TOC → EOS V1 → titles."""
    job_path = Path(job_dir)
    job_path.mkdir(parents=True, exist_ok=True)
    job_id = job_path.name
    t_run0 = monotonic()
    executed: dict[str, Path] = {}

    os.environ.setdefault("OMP_NUM_THREADS", "2")
    os.environ.setdefault("MKL_NUM_THREADS", "2")
    os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")

    # --- source ---
    if source_audio is not None:
        source_path = Path(source_audio)
    else:
        candidates = [
            f
            for f in job_path.iterdir()
            if f.is_file()
            and f.name not in {"normalized.wav", "vad_input.wav"}
            and not f.name.endswith(".json")
            and not f.name.startswith(".")
            and not f.name.startswith("_")
        ]
        if not candidates:
            raise FileNotFoundError(f"No source audio file found in {job_path}")
        source_path = candidates[0]

    # --- normalize (file_max_db) ---
    _emit(events, StageEvent(stage="normalize", status="running", pct=0))
    t0 = monotonic()
    normalizer = FfmpegAudioNormalizer()
    audio_art = normalizer.normalize(
        source=source_path,
        dest=job_path,
        cfg=cfg.audio,
        job_id=job_id,
        file_gain_max_db=cfg.audio.gain.file_max_db,
    )
    executed["normalize"] = job_path / "audio.json"
    _emit(
        events,
        StageEvent(
            stage="normalize",
            status="done",
            pct=100,
            runtime_sec=round(monotonic() - t0, 3),
            message=f"file_max_db capped={audio_art.loudness.capped}",
        ),
    )
    if until == "normalize":
        return executed

    duration_sec = float(sf.info(str(job_path / "normalized.wav")).duration)

    # --- VAD once ---
    _emit(events, StageEvent(stage="vad", status="running", pct=0))
    t0 = monotonic()
    vad_name = audio_art.vad_input.path if audio_art.vad_input.path else "vad_input.wav"
    vad_wav = job_path / vad_name
    if not vad_wav.is_file():
        vad_wav = job_path / "normalized.wav"
    detector = build("vad", cfg.vad.engine, cfg.app.profile)
    detector.detect(vad_wav, cfg.vad, job_id=job_id)
    speech = load_artifact(job_path / "speech.json", SpeechArtifact)
    executed["vad"] = job_path / "speech.json"
    _emit(
        events,
        StageEvent(
            stage="vad",
            status="done",
            pct=100,
            runtime_sec=round(monotonic() - t0, 3),
        ),
    )
    if until == "vad":
        return executed

    # --- cut plan ---
    ttft = cfg.pipeline.ttft
    regions = [(r.start, r.end) for r in speech.regions]
    n_parts = propose_n_parts(
        duration_sec,
        min_part_sec=ttft.min_part_sec,
        max_part_sec=ttft.max_part_sec,
        target_part_sec=ttft.target_part_sec,
    )
    cut_plan = plan(
        regions,
        duration_sec=duration_sec,
        n_parts=n_parts,
        min_part_sec=ttft.min_part_sec,
        max_part_sec=ttft.max_part_sec,
        min_pause_sec=ttft.min_pause_sec,
        search_half_width=ttft.search_half_width_sec,
    )
    _atomic_json(job_path / CUT_PLAN_JSON, cut_plan)
    logger.info(
        "ttft cut_plan n_parts=%s durations=%s job_id=%s",
        n_parts,
        cut_plan["metrics"]["part_durations_sec"],
        job_id,
    )

    parts_dir = job_path / "parts"
    parts_dir.mkdir(parents=True, exist_ok=True)
    full_wav = job_path / "normalized.wav"

    gallery: SpeakerGallery | None = None
    threshold = float(cfg.diarization.embed.cluster_distance_threshold)
    all_abs_turns: list[TurnItem] = []
    all_segments: list[TranscriptSegment] = []
    published_order: list[str] = []
    early_published = False
    diarizer = WeSpeakerDiarizer()
    embedder = build("embeddings", cfg.chunking.embedding_model, cfg.app.profile)
    client = make_client(cfg.llm) if until in {"titles", "insights_extract", "report"} else None

    titled_slots: dict[int, str] = {}
    title_calls = 0

    def _maybe_title(chapters: list[ChapterItem], *, close_all: bool) -> None:
        nonlocal title_calls
        if client is None:
            return
        limit = len(chapters) if close_all else max(0, len(chapters) - 1)
        for slot in range(limit):
            if slot in titled_slots:
                continue
            chapter = chapters[slot]
            if chapter.title.strip():
                titled_slots[slot] = chapter.title
                continue
            tr = TranscriptArtifact(
                schema_version="1",
                job_id=job_id,
                engine="gigaam_v3_rnnt",
                language="ru",
                segments=list(all_segments),
                holes=[],
                max_segment_sec=cfg.asr.max_segment_seconds,
                runtime_sec=0.0,
            )
            try:
                title, used = title_one_chapter(
                    chapter,
                    tr,
                    client,
                    cfg.llm,
                    used_titles=None,
                    calls_so_far=title_calls,
                )
                title_calls += used
                titled_slots[slot] = title
                chapters[slot] = chapter.model_copy(update={"title": title})
            except Exception as exc:
                logger.warning("ttft title failed slot=%s err=%s", slot, exc)

    _emit(events, StageEvent(stage="diarize", status="running", pct=0))
    diar_t0 = monotonic()
    asr_wall = 0.0

    for part in cut_plan["parts"]:
        part_id = str(part["id"])
        part_start = float(part["start"])
        part_end = float(part["end"])
        is_last = part is cut_plan["parts"][-1]
        part_dir = parts_dir / part_id
        part_dir.mkdir(parents=True, exist_ok=True)
        part_wav = part_dir / "part.wav"
        _slice_wav(full_wav, part_wav, part_start, part_end)
        part_speech = _speech_for_part(
            speech, part_start=part_start, part_end=part_end, job_id=f"{job_id}:{part_id}"
        )
        dump_artifact(part_speech, part_dir / "speech.json")

        # --- diarize method B ---
        t_diar = monotonic()
        embedder_ws = diarizer._get_embedder()
        rel_segments, embeddings = extract_wespeaker_windows(
            part_wav, part_speech, cfg.diarization, embedder_ws
        )
        part_dur = round(part_end - part_start, 3)

        if not rel_segments:
            part_turns = TurnsArtifact(
                schema_version="1",
                job_id=job_id,
                diarizer="wespeaker_onnx",
                speaker_count=0,
                turns=[],
                holes=[],
                merge=TurnMergeInfo(
                    same_speaker_gap_sec=cfg.diarization.merge.same_speaker_gap_sec,
                    absorb_shorter_than_sec=cfg.diarization.merge.absorb_turn_shorter_than_sec,
                ),
                runtime_sec=round(monotonic() - t_diar, 3),
            )
            mid_for_windows = []
            abs_segments = []
            if gallery is None:
                gallery = SpeakerGallery(threshold=threshold)
                _atomic_json(job_path / CENTROIDS_JSON, gallery.to_json())
        elif gallery is None or not gallery.speakers:
            # First part with speech: AHC
            raw_labels = ahc_labels(embeddings, threshold)
            raw_ids = [f"SPEAKER_{int(lbl):02d}" for lbl in raw_labels]
            part_turns = turns_from_window_speakers(
                rel_segments,
                raw_ids,
                cfg.diarization,
                job_id=job_id,
                total_duration=part_dur,
                runtime_sec=round(monotonic() - t_diar, 3),
                compact_renumber=True,
            )
            mid_for_windows = window_speakers_after_turns(
                rel_segments, raw_ids, part_turns.turns
            )
            gallery = SpeakerGallery.from_ahc(embeddings, mid_for_windows, threshold)
            _atomic_json(job_path / CENTROIDS_JSON, gallery.to_json())
            published_order = [s["id"] for s in gallery.speakers]
            abs_segments = [
                (round(s + part_start, 3), round(e + part_start, 3)) for s, e in rel_segments
            ]
        else:
            # Part2+ nearest centroid (method B) — do not compact-renumber
            speaker_ids, _summary = gallery.assign(embeddings)
            part_turns = turns_from_window_speakers(
                rel_segments,
                speaker_ids,
                cfg.diarization,
                job_id=job_id,
                total_duration=part_dur,
                runtime_sec=round(monotonic() - t_diar, 3),
                compact_renumber=False,
            )
            mid_for_windows = window_speakers_after_turns(
                rel_segments, speaker_ids, part_turns.turns
            )
            _atomic_json(job_path / CENTROIDS_JSON, gallery.to_json())
            for sid in (s["id"] for s in gallery.speakers):
                if sid not in published_order:
                    published_order.append(sid)
            abs_segments = [
                (round(s + part_start, 3), round(e + part_start, 3)) for s, e in rel_segments
            ]

        if abs_segments and len(embeddings):
            _append_windows(job_path, abs_segments, embeddings, mid_for_windows)

        abs_turns = _shift_turns_abs(
            part_turns,
            part_start,
            job_id=job_id,
            total_duration=duration_sec,
            min_hole_sec=cfg.diarization.merge.min_hole_sec,
        )
        # Re-id turns uniquely across parts
        renumbered: list[TurnItem] = []
        base = len(all_abs_turns)
        for i, turn in enumerate(abs_turns.turns):
            renumbered.append(
                TurnItem(
                    id=f"T{base + i:04d}",
                    start=turn.start,
                    end=turn.end,
                    speaker=turn.speaker,
                )
            )
        all_abs_turns.extend(renumbered)
        dump_artifact(
            TurnsArtifact(
                schema_version="1",
                job_id=job_id,
                diarizer="wespeaker_onnx",
                speaker_count=len({t.speaker for t in all_abs_turns}),
                turns=list(all_abs_turns),
                holes=find_holes(
                    all_abs_turns, duration_sec, cfg.diarization.merge.min_hole_sec
                ),
                merge=TurnMergeInfo(
                    same_speaker_gap_sec=cfg.diarization.merge.same_speaker_gap_sec,
                    absorb_shorter_than_sec=cfg.diarization.merge.absorb_turn_shorter_than_sec,
                ),
                runtime_sec=round(monotonic() - diar_t0, 3),
            ),
            job_path / "turns.json",
        )
        dump_artifact(abs_turns.model_copy(update={"turns": renumbered}), part_dir / "turns.json")

        if until == "diarize" and is_last:
            executed["diarize"] = job_path / "turns.json"
            _emit(
                events,
                StageEvent(
                    stage="diarize",
                    status="done",
                    pct=100,
                    runtime_sec=round(monotonic() - diar_t0, 3),
                ),
            )
            return executed

        # --- ASR on part (relative turns on part wav) ---
        _emit(events, StageEvent(stage="asr", status="running", pct=10))
        t_asr = monotonic()
        # Relative turns for ASR (ids local)
        rel_turn_items = [
            TurnItem(
                id=f"P{turn.id}",
                start=round(turn.start - part_start, 3),
                end=round(turn.end - part_start, 3),
                speaker=turn.speaker,
            )
            for turn in renumbered
            if turn.end > part_start and turn.start < part_end
        ]
        # Clamp to part-local bounds
        clamped: list[TurnItem] = []
        for turn in rel_turn_items:
            a = max(0.0, turn.start)
            b = min(part_dur, turn.end)
            if b > a + 1e-3:
                clamped.append(TurnItem(id=turn.id, start=a, end=b, speaker=turn.speaker))
        part_turns_rel = TurnsArtifact(
            schema_version="1",
            job_id=job_id,
            diarizer="wespeaker_onnx",
            speaker_count=len({t.speaker for t in clamped}),
            turns=clamped,
            holes=[],
            merge=TurnMergeInfo(
                same_speaker_gap_sec=cfg.diarization.merge.same_speaker_gap_sec,
                absorb_shorter_than_sec=cfg.diarization.merge.absorb_turn_shorter_than_sec,
            ),
            runtime_sec=0.0,
        )
        audio_meta = load_artifact(job_path / "audio.json", AudioArtifact)
        part_transcript = transcribe_slices_with_model(
            wav_path=part_wav,
            turns=part_turns_rel,
            max_segment_sec=cfg.asr.max_segment_seconds,
            gain_db=float(audio_meta.loudness.gain_db),
            per_turn_gain=bool(audio_meta.asr_per_turn_gain),
            gain_rms_threshold_dbfs=cfg.audio.gain.rms_threshold_dbfs,
            gain_target_dbfs=cfg.audio.gain.target_dbfs,
            gain_max_db=cfg.audio.gain.max_db,
            gain_peak_ceiling_dbfs=cfg.audio.gain.peak_ceiling_dbfs,
            job_id=job_id,
        )
        asr_wall += monotonic() - t_asr
        part_segs = _shift_segments(
            part_transcript.segments, part_start, id_prefix=part_id
        )
        # Remap speaker ids already absolute; keep as-is
        # Map segment speakers from absolute turns covering midpoint
        fixed_segs: list[TranscriptSegment] = []
        for seg in part_segs:
            mid = (seg.start + seg.end) / 2.0
            spk = _speaker_at(renumbered, mid) or seg.speaker
            fixed_segs.append(seg.model_copy(update={"speaker": spk}))
        part_segs = fixed_segs

        # --- packing (all segments so far; absorb only on last part / EOS) ---
        all_segments.extend(part_segs)
        publish_chapters = _buffer_to_chapters(
            all_segments, embedder, cfg, apply_absorb=is_last
        )

        turns_art = load_artifact(job_path / "turns.json", TurnsArtifact)
        transcript_art = TranscriptArtifact(
            schema_version="1",
            job_id=job_id,
            engine="gigaam_v3_rnnt",
            language="ru",
            segments=list(all_segments),
            holes=list(turns_art.holes),
            max_segment_sec=cfg.asr.max_segment_seconds,
            runtime_sec=round(asr_wall, 3),
        )
        dump_artifact(transcript_art, job_path / "transcript.json")

        for i, ch in enumerate(publish_chapters):
            if i in titled_slots:
                publish_chapters[i] = ch.model_copy(update={"title": titled_slots[i]})

        if publish_chapters and until in {
            "chunk",
            "titles",
            "insights_extract",
            "report",
            "asr",
        }:
            _write_chapters(
                job_path,
                job_id,
                publish_chapters,
                cfg,
                embedder,
                runtime_sec=monotonic() - t_run0,
            )

        # Early publish after part1
        if part["index"] == 0 and publish_chapters and not early_published:
            _patch_job_flags(job_path, early_ready=True, speakers_finalized=False)
            _atomic_json(
                job_path / TTFT_MARK_JSON,
                {
                    "ttft_first_chapter_sec": round(monotonic() - t_run0, 3),
                    "part_id": part_id,
                    "n_chapters": len(publish_chapters),
                },
            )
            early_published = True
            _emit(
                events,
                StageEvent(
                    stage="chunk",
                    status="done",
                    pct=100,
                    message="ttft_part1",
                    runtime_sec=round(monotonic() - t_run0, 3),
                ),
            )
            logger.info(
                "ttft early_ready job_id=%s chapters=%s wall=%.1f",
                job_id,
                len(publish_chapters),
                monotonic() - t_run0,
            )
            if client is not None and len(publish_chapters) > 1:
                _maybe_title(publish_chapters, close_all=False)
                for i, ch in enumerate(publish_chapters):
                    if i in titled_slots:
                        publish_chapters[i] = ch.model_copy(update={"title": titled_slots[i]})
                _write_chapters(
                    job_path,
                    job_id,
                    publish_chapters,
                    cfg,
                    embedder,
                    runtime_sec=monotonic() - t_run0,
                )
        elif early_published and client is not None and not is_last:
            _maybe_title(publish_chapters, close_all=False)

        executed["asr"] = job_path / "transcript.json"
        executed["chunk"] = job_path / "chapters.json"
        logger.info(
            "ttft part done id=%s turns=%s segs=%s chapters=%s",
            part_id,
            len(renumbered),
            len(part_segs),
            len(publish_chapters),
        )

    _emit(
        events,
        StageEvent(
            stage="diarize",
            status="done",
            pct=100,
            runtime_sec=round(monotonic() - diar_t0, 3),
            message="ttft_method_b",
        ),
    )
    executed["diarize"] = job_path / "turns.json"
    if until == "diarize":
        return executed
    if until == "asr":
        return executed

    # --- EOS V1 ---
    win_segs, win_emb, mid_spk = _load_windows(job_path)
    if win_segs:
        final_window_spk, eos_summary = refine_window_speakers_v1(
            win_emb,
            win_segs,
            mid_spk,
            distance_threshold=threshold,
            published_order=published_order,
        )
        _atomic_json(job_path / "eos_remap.json", eos_summary)
        eos_turns = turns_from_window_speakers(
            win_segs,
            final_window_spk,
            cfg.diarization,
            job_id=job_id,
            total_duration=duration_sec,
            runtime_sec=0.0,
            compact_renumber=False,
        )
        dump_artifact(eos_turns, job_path / "turns.json")
        transcript = load_artifact(job_path / "transcript.json", TranscriptArtifact)
        transcript = _apply_speaker_map_to_transcript(transcript, eos_turns.turns)
        dump_artifact(transcript, job_path / "transcript.json")
        if (job_path / "chapters.json").is_file():
            chapters_art = load_artifact(job_path / "chapters.json", ChaptersArtifact)
            new_chs = _rewrite_chapter_speakers(chapters_art.chapters, transcript)
            dump_artifact(
                chapters_art.model_copy(update={"chapters": new_chs}),
                job_path / "chapters.json",
            )
        all_segments = list(transcript.segments)
    _patch_job_flags(job_path, speakers_finalized=True)
    logger.info("ttft EOS speakers_finalized job_id=%s", job_id)

    # Final packing absorb (+ titles when requested)
    if until in {"titles", "insights_extract", "report", "chunk"}:
        final_chapters = _buffer_to_chapters(
            all_segments, embedder, cfg, apply_absorb=True
        )
        for i, ch in enumerate(final_chapters):
            if i in titled_slots:
                final_chapters[i] = ch.model_copy(update={"title": titled_slots[i]})
        if client is not None and until in {"titles", "insights_extract", "report"}:
            _emit(events, StageEvent(stage="titles", status="running", pct=0))
            _maybe_title(final_chapters, close_all=True)
            for i, ch in enumerate(final_chapters):
                if i in titled_slots:
                    final_chapters[i] = ch.model_copy(update={"title": titled_slots[i]})
            for i, ch in enumerate(final_chapters):
                if not ch.title.strip():
                    final_chapters[i] = ch.model_copy(update={"title": f"Глава {i + 1}"})
            _emit(
                events,
                StageEvent(stage="titles", status="done", pct=100, message="ttft_eos"),
            )
            executed["titles"] = job_path / "chapters.json"
        _write_chapters(
            job_path,
            job_id,
            final_chapters,
            cfg,
            embedder,
            runtime_sec=monotonic() - t_run0,
        )
        executed["chunk"] = job_path / "chapters.json"

    return executed

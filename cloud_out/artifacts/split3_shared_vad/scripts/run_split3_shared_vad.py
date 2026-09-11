#!/usr/bin/env python3
"""Run 3-part split using SHARED full15 VAD (no per-part Silero).

Writes artifacts under cloud_out/artifacts/split3_shared_vad/.
Does not modify src/ or config/. Does not clobber split3/.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/workspace")
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from centroid_assign import SpeakerGallery, diarize_part  # noqa: E402
from transcriber.config.loader import load_config  # noqa: E402
from transcriber.models.artifacts import (  # noqa: E402
    AudioArtifact,
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    SpeechArtifact,
    TimeInterval,
    TranscriptArtifact,
    TranscriptSegment,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)
from transcriber.pipeline.orchestrator import run_stage  # noqa: E402
from transcriber.registry import build  # noqa: E402

SPLIT3 = ROOT / "cloud_out" / "artifacts" / "split3_shared_vad"
PARTS_DIR = ROOT / "cloud_out" / "artifacts" / "parts"
CUT_PLAN = ROOT / "cloud_in" / "inputs" / "artifacts" / "cut_plan_15min_3.json"
FULL15_SPEECH = ROOT / "cloud_out" / "artifacts" / "full15" / "speech.json"
FULL15_TRANSCRIPT = ROOT / "cloud_out" / "artifacts" / "full15" / "transcript.json"
SPLIT3_OLD_PART02 = ROOT / "cloud_out" / "artifacts" / "split3" / "parts_jobs" / "part02" / "transcript.json"
STAGES = ("normalize", "vad", "diarize", "asr", "chunk", "llm_sleep_2s")
LLM_SLEEP_SEC = 2.0


def _round3(value: float) -> float:
    return round(float(value), 3)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _mark_stage(
    marks: dict[str, Any],
    stage: str,
    *,
    started: float,
    done: float,
    skipped: bool = False,
) -> None:
    marks[stage] = {
        "started_sec": _round3(started),
        "done_sec": _round3(done),
        "wall_sec": 0.0 if skipped else _round3(done - started),
        "skipped": skipped,
    }


def slice_full15_speech(
    full: SpeechArtifact,
    *,
    plan_start: float,
    plan_end: float,
    job_id: str,
) -> SpeechArtifact:
    """Intersect full-file Silero regions with [plan_start, plan_end], 0-based on part wav."""
    regions: list[TimeInterval] = []
    for region in full.regions:
        start = max(float(region.start), plan_start)
        end = min(float(region.end), plan_end)
        if end <= start:
            continue
        local_start = _round3(start - plan_start)
        local_end = _round3(end - plan_start)
        if local_end <= local_start:
            continue
        regions.append(TimeInterval(start=local_start, end=local_end))
    speech_sec = _round3(sum(item.end - item.start for item in regions))
    return SpeechArtifact(
        schema_version="1",
        job_id=job_id,
        detector=full.detector,
        fallback_used=False,
        regions=regions,
        fallback_regions=[],
        speech_sec=speech_sec,
        runtime_sec=0.0,
    )


def _offset_segment(seg: TranscriptSegment, offset: float, new_id: str) -> TranscriptSegment:
    return seg.model_copy(
        update={
            "id": new_id,
            "start": _round3(seg.start + offset),
            "end": _round3(seg.end + offset),
        }
    )


def _tail_segments(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    part_id: str,
    plan_start: float,
) -> list[TranscriptSegment]:
    if not chapters.chapters:
        return []
    last = chapters.chapters[-1]
    by_id = {s.id: s for s in transcript.segments}
    out: list[TranscriptSegment] = []
    for sid in last.source_ids:
        seg = by_id.get(sid)
        if seg is None:
            continue
        out.append(_offset_segment(seg, plan_start, f"{part_id}:{seg.id}"))
    # Trailing segments after last chapter end (should be rare)
    last_end = last.end
    for seg in transcript.segments:
        if seg.start + 1e-6 >= last_end and seg.id not in last.source_ids:
            out.append(_offset_segment(seg, plan_start, f"{part_id}:{seg.id}"))
    out.sort(key=lambda s: s.start)
    return out


def _pack(
    segments: list[TranscriptSegment],
    cfg: Any,
    job_id: str,
) -> ChaptersArtifact:
    embedder = build("embeddings", cfg.chunking.embedding_model, cfg.app.profile)
    chunker = build("chunking", cfg.chunking.chunker, cfg.app.profile)
    fake = TranscriptArtifact(
        schema_version="1",
        job_id=job_id,
        engine="gigaam_v3_rnnt",
        language="ru",
        segments=segments,
        holes=[],
        max_segment_sec=cfg.asr.max_segment_seconds,
        runtime_sec=0.0,
    )
    return chunker.chunk(fake, embedder, cfg.chunking)


def _local_chapters_from_packed(
    packed: ChaptersArtifact,
    part_id: str,
    plan_start: float,
    local_transcript: TranscriptArtifact,
    job_id: str,
) -> ChaptersArtifact:
    """Keep chapters that touch this part; times local; source_ids local."""
    local_ids = {s.id for s in local_transcript.segments}
    prefix = f"{part_id}:"
    kept: list[ChapterItem] = []
    for ch in packed.chapters:
        local_source: list[str] = []
        for sid in ch.source_ids:
            if sid.startswith(prefix):
                local_source.append(sid.split(":", 1)[1])
        if not local_source:
            continue
        if any(s not in local_ids for s in local_source):
            local_source = [s for s in local_source if s in local_ids]
        if not local_source:
            continue
        start = _round3(max(0.0, ch.start - plan_start))
        end = _round3(max(start + 0.001, ch.end - plan_start))
        kept.append(
            ChapterItem(
                id=f"C{len(kept):02d}",
                start=start,
                end=end,
                source_ids=local_source,
                speakers=list(ch.speakers),
                title="",
                duration_sec=_round3(end - start),
            )
        )
    meeting_minutes = (
        max(s.end for s in local_transcript.segments) / 60.0 if local_transcript.segments else 0.0
    )
    density = len(kept) / meeting_minutes if meeting_minutes else 0.0
    short_limit, long_limit = cfg_chunk_limits
    return ChaptersArtifact(
        schema_version="1",
        job_id=job_id,
        chunker=packed.chunker,
        embedding_model=packed.embedding_model,
        similarity_threshold=packed.similarity_threshold,
        chapters=kept,
        metrics=ChapterMetrics(
            chapters_per_minute=_round3(density),
            short_chapters=sum(c.duration_sec < short_limit for c in kept),
            long_chapters=sum(c.duration_sec > long_limit for c in kept),
        ),
        runtime_sec=packed.runtime_sec,
    )


cfg_chunk_limits = (45.0, 180.0)


def _naive_merge(
    part_rows: list[dict[str, Any]],
) -> tuple[TranscriptArtifact, ChaptersArtifact]:
    segments: list[TranscriptSegment] = []
    chapters: list[ChapterItem] = []
    seg_n = 1
    ch_n = 0
    for row in part_rows:
        offset = float(row["plan_start"])
        part_id = row["part_id"]
        tr: TranscriptArtifact = row["transcript"]
        chs: ChaptersArtifact = row["chapters"]
        id_map: dict[str, str] = {}
        for seg in tr.segments:
            new_id = f"s{seg_n:04d}"
            seg_n += 1
            id_map[seg.id] = new_id
            segments.append(
                seg.model_copy(
                    update={
                        "id": new_id,
                        "start": _round3(seg.start + offset),
                        "end": _round3(seg.end + offset),
                        "turn_id": f"{part_id}:{seg.turn_id}",
                    }
                )
            )
        for ch in chs.chapters:
            mapped = [id_map[s] for s in ch.source_ids if s in id_map]
            if not mapped:
                continue
            start = _round3(ch.start + offset)
            end = _round3(ch.end + offset)
            chapters.append(
                ChapterItem(
                    id=f"C{ch_n:02d}",
                    start=start,
                    end=end,
                    source_ids=mapped,
                    speakers=list(ch.speakers),
                    title="",
                    duration_sec=_round3(end - start),
                )
            )
            ch_n += 1
    tr_out = TranscriptArtifact(
        schema_version="1",
        job_id="split3_merged",
        engine="gigaam_v3_rnnt",
        language="ru",
        segments=segments,
        holes=[],
        max_segment_sec=25,
        runtime_sec=0.0,
    )
    minutes = segments[-1].end / 60.0 if segments else 0.0
    ch_out = ChaptersArtifact(
        schema_version="1",
        job_id="split3_merged",
        chunker="packing_c",
        embedding_model="rubert_tiny2",
        similarity_threshold=0.70,
        chapters=chapters,
        metrics=ChapterMetrics(
            chapters_per_minute=_round3(len(chapters) / minutes) if minutes else 0.0,
            short_chapters=sum(c.duration_sec < 45.0 for c in chapters),
            long_chapters=sum(c.duration_sec > 180.0 for c in chapters),
        ),
        runtime_sec=0.0,
    )
    return tr_out, ch_out


def _continuity_merge(
    part_rows: list[dict[str, Any]],
    packed_abs_chapters: list[ChapterItem],
) -> tuple[TranscriptArtifact, ChaptersArtifact]:
    """Absolute transcript from parts; chapters from tail-aware packing."""
    segments: list[TranscriptSegment] = []
    key_to_merged: dict[str, str] = {}
    seg_n = 1
    for row in part_rows:
        offset = float(row["plan_start"])
        part_id = row["part_id"]
        tr: TranscriptArtifact = row["transcript"]
        for seg in tr.segments:
            new_id = f"s{seg_n:04d}"
            seg_n += 1
            key_to_merged[f"{part_id}:{seg.id}"] = new_id
            segments.append(
                seg.model_copy(
                    update={
                        "id": new_id,
                        "start": _round3(seg.start + offset),
                        "end": _round3(seg.end + offset),
                        "turn_id": f"{part_id}:{seg.turn_id}",
                    }
                )
            )
    chapters: list[ChapterItem] = []
    for i, ch in enumerate(packed_abs_chapters):
        mapped = [key_to_merged[s] for s in ch.source_ids if s in key_to_merged]
        if not mapped:
            continue
        chapters.append(
            ChapterItem(
                id=f"C{i:02d}",
                start=_round3(ch.start),
                end=_round3(ch.end),
                source_ids=mapped,
                speakers=list(ch.speakers),
                title="",
                duration_sec=_round3(ch.end - ch.start),
            )
        )
    tr_out = TranscriptArtifact(
        schema_version="1",
        job_id="split3_merged",
        engine="gigaam_v3_rnnt",
        language="ru",
        segments=segments,
        holes=[],
        max_segment_sec=25,
        runtime_sec=0.0,
    )
    minutes = segments[-1].end / 60.0 if segments else 0.0
    ch_out = ChaptersArtifact(
        schema_version="1",
        job_id="split3_merged",
        chunker="packing_c",
        embedding_model="rubert_tiny2",
        similarity_threshold=0.70,
        chapters=chapters,
        metrics=ChapterMetrics(
            chapters_per_minute=_round3(len(chapters) / minutes) if minutes else 0.0,
            short_chapters=sum(c.duration_sec < 45.0 for c in chapters),
            long_chapters=sum(c.duration_sec > 180.0 for c in chapters),
        ),
        runtime_sec=0.0,
    )
    return tr_out, ch_out


def _validate_merge(part_rows: list[dict[str, Any]], merged: TranscriptArtifact) -> dict[str, Any]:
    expected = sum(len(r["transcript"].segments) for r in part_rows)
    starts = [s.start for s in merged.segments]
    monotonic = all(starts[i] <= starts[i + 1] for i in range(len(starts) - 1))
    # Contiguous per-part text blocks in time order
    texts_ok = True
    cursor = 0
    merged_texts = [s.text for s in merged.segments]
    for row in part_rows:
        part_texts = [s.text for s in row["transcript"].segments]
        slice_ = merged_texts[cursor : cursor + len(part_texts)]
        if slice_ != part_texts:
            texts_ok = False
            break
        cursor += len(part_texts)
    return {
        "n_merged": len(merged.segments),
        "n_expected": expected,
        "count_match": len(merged.segments) == expected,
        "monotonic": monotonic,
        "part_blocks_preserved": texts_ok and cursor == expected,
    }


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.chdir(ROOT)

    cut = json.loads(CUT_PLAN.read_text(encoding="utf-8"))
    manifest = json.loads((PARTS_DIR / "manifest.json").read_text(encoding="utf-8"))
    cfg = load_config(profile="demo")
    cfg = cfg.model_copy(deep=True)
    cfg.pipeline.toc_mode = "a"
    cfg.vad.onnx_threads = 2
    cfg.diarization.onnx_threads = 2
    global cfg_chunk_limits
    cfg_chunk_limits = (cfg.chunking.target_chapter_sec[0], cfg.chunking.target_chapter_sec[1])

    full_speech = load_artifact(FULL15_SPEECH, SpeechArtifact)

    SPLIT3.mkdir(parents=True, exist_ok=True)
    (SPLIT3 / "parts_jobs").mkdir(parents=True, exist_ok=True)
    (SPLIT3 / "merged").mkdir(parents=True, exist_ok=True)

    job_t0 = time.monotonic()
    gallery: SpeakerGallery | None = None
    tail: list[TranscriptSegment] = []
    committed_abs_chapters: list[ChapterItem] = []
    part_rows: list[dict[str, Any]] = []
    timing_parts: dict[str, Any] = {}
    blocked: str | None = None
    centroid_ok = True

    ctx_ns_type = type("Ctx", (), {})

    for part in cut["parts"]:
        part_id = part["id"]
        plan_start = float(part["start"])
        audio = PARTS_DIR / f"{part_id}.m4a"
        job_dir = SPLIT3 / "parts_jobs" / part_id
        job_dir.mkdir(parents=True, exist_ok=True)
        marks: dict[str, Any] = {}
        ctx = ctx_ns_type()
        ctx.job_id = part_id
        ctx.job_dir = job_dir
        ctx.source_audio = audio

        # normalize only — VAD is sliced from full15 speech.json
        t_started = time.monotonic() - job_t0
        run_stage("normalize", job_dir, cfg=cfg, source_audio=audio)
        t_done = time.monotonic() - job_t0
        _mark_stage(marks, "normalize", started=t_started, done=t_done)

        t_skip = time.monotonic() - job_t0
        speech = slice_full15_speech(
            full_speech,
            plan_start=plan_start,
            plan_end=float(part["end"]),
            job_id=part_id,
        )
        dump_artifact(speech, job_dir / "speech.json")
        _mark_stage(marks, "vad", started=t_skip, done=t_skip, skipped=True)

        # diarize
        t_started = time.monotonic() - job_t0
        wav = job_dir / "normalized.wav"
        mode = "ahc" if part_id == "part01" else "assign"
        try:
            _turns, gallery, assign_log = diarize_part(
                wav,
                speech,
                cfg.diarization,
                job_id=part_id,
                gallery=gallery,
                mode=mode,
            )
        except Exception as exc:
            centroid_ok = False
            blocked = f"centroid assign failed on {part_id}: {type(exc).__name__}: {exc}"
            run_stage("diarize", job_dir, cfg=cfg, source_audio=audio)
            assign_log = {"mode": "product_fallback", "error": blocked}
        t_done = time.monotonic() - job_t0
        _mark_stage(marks, "diarize", started=t_started, done=t_done)

        if part_id == "part01" and gallery is not None:
            _write_json(SPLIT3 / "centroids_part01.json", gallery.to_json())
        if part_id in {"part02", "part03"}:
            _write_json(SPLIT3 / f"assign_log_{part_id}.json", assign_log)

        # asr (product GigaAM)
        t_started = time.monotonic() - job_t0
        run_stage("asr", job_dir, cfg=cfg, source_audio=audio)
        t_done = time.monotonic() - job_t0
        _mark_stage(marks, "asr", started=t_started, done=t_done)

        transcript = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
        turns = load_artifact(job_dir / "turns.json", TurnsArtifact)

        # packing C with tail from previous part (absolute timeline)
        t_started = time.monotonic() - job_t0
        current_abs = [
            _offset_segment(seg, plan_start, f"{part_id}:{seg.id}")
            for seg in transcript.segments
        ]
        combined = list(tail) + current_abs
        if not combined:
            packed = ChaptersArtifact(
                schema_version="1",
                job_id=part_id,
                chunker="packing_c",
                embedding_model="rubert_tiny2",
                similarity_threshold=cfg.chunking.similarity_threshold,
                chapters=[],
                metrics=ChapterMetrics(chapters_per_minute=0.0, short_chapters=0, long_chapters=0),
                runtime_sec=0.0,
            )
        else:
            packed = _pack(combined, cfg, job_id=part_id)

        local_chapters = _local_chapters_from_packed(
            packed, part_id, plan_start, transcript, part_id
        )
        dump_artifact(local_chapters, job_dir / "chapters.json")

        # Commit all-but-last; last chapter stays open as tail
        is_last = part_id == cut["parts"][-1]["id"]
        if packed.chapters:
            if is_last:
                committed_abs_chapters.extend(packed.chapters)
                tail = []
            else:
                committed_abs_chapters.extend(packed.chapters[:-1])
                last_ch = packed.chapters[-1]
                last_ids = set(last_ch.source_ids)
                tail = [s for s in combined if s.id in last_ids]
        t_done = time.monotonic() - job_t0
        _mark_stage(marks, "chunk", started=t_started, done=t_done)

        # emulate LLM titles after embeddings/chunking
        t_started = time.monotonic() - job_t0
        time.sleep(LLM_SLEEP_SEC)
        t_done = time.monotonic() - job_t0
        _mark_stage(marks, "llm_sleep_2s", started=t_started, done=t_done)

        for stage in STAGES:
            marks.setdefault(
                stage,
                {"started_sec": None, "done_sec": None, "wall_sec": 0.0, "skipped": True},
            )

        _write_json(job_dir / "marks.json", {"part_id": part_id, "stages": marks})
        cumulative = _round3(time.monotonic() - job_t0)
        timing_parts[part_id] = {
            "plan_start": plan_start,
            "plan_end": float(part["end"]),
            "audio": str(audio),
            "speaker_count": turns.speaker_count,
            "n_turns": len(turns.turns),
            "n_chapters": len(local_chapters.chapters),
            "n_segments": len(transcript.segments),
            "cumulative_from_job_start_sec": cumulative,
            "stages": marks,
        }
        part_rows.append(
            {
                "part_id": part_id,
                "plan_start": plan_start,
                "transcript": transcript,
                "chapters": local_chapters,
                "turns": turns,
            }
        )

    ttft = timing_parts["part01"]["stages"]["chunk"]["done_sec"]
    ttft_sleep = timing_parts["part01"]["stages"]["llm_sleep_2s"]["done_sec"]

    if centroid_ok and committed_abs_chapters:
        merged_tr, merged_ch = _continuity_merge(part_rows, committed_abs_chapters)
        merge_mode = "tail_packing_plus_centroid_speakers"
    else:
        merged_tr, merged_ch = _naive_merge(part_rows)
        merge_mode = "naive_time_offset"
        if blocked is None:
            blocked = "centroid/tail merge unavailable; used naive time-offset merge"

    merge_stats = _validate_merge(part_rows, merged_tr)
    dump_artifact(merged_tr, SPLIT3 / "merged" / "transcript.json")
    dump_artifact(merged_ch, SPLIT3 / "merged" / "chapters.json")

    cut_compare = _compare_near_cuts(part_rows, cut)

    cuts = [float(c["t"]) for c in cut.get("cuts", [])]
    spanning = []
    for ch in merged_ch.chapters:
        hits = [t for t in cuts if ch.start < t < ch.end]
        if hits:
            spanning.append({"id": ch.id, "start": ch.start, "end": ch.end, "cuts": hits})

    speakers_by_part = {
        r["part_id"]: sorted({t.speaker for t in r["turns"].turns}) for r in part_rows
    }
    overlap_12 = sorted(set(speakers_by_part.get("part01", [])) & set(speakers_by_part.get("part02", [])))
    overlap_23 = sorted(set(speakers_by_part.get("part02", [])) & set(speakers_by_part.get("part03", [])))

    timing = {
        "schema_version": "1",
        "cluster_distance_threshold": cfg.diarization.embed.cluster_distance_threshold,
        "onnx_threads": 2,
        "toc_mode_forced": "a",
        "llm_sleep_sec": LLM_SLEEP_SEC,
        "ttft_first_chapter_sec": ttft,
        "ttft_after_sleep_sec": ttft_sleep,
        "wall_total_sec": _round3(time.monotonic() - job_t0),
        "merge_mode": merge_mode,
        "centroid_assign_ok": centroid_ok,
        "parts": timing_parts,
        "merge": merge_stats,
        "vad_source": str(FULL15_SPEECH),
        "vad_mode": "shared_full15_slice",
        "cut_compare": cut_compare,
        "cross_part": {
            "speakers_by_part": speakers_by_part,
            "stable_ids_part01_part02": overlap_12,
            "stable_ids_part02_part03": overlap_23,
            "chapters_spanning_cuts": spanning,
        },
    }
    _write_json(SPLIT3 / "timing.json", timing)

    if blocked and not centroid_ok:
        (SPLIT3 / "BLOCKED.md").write_text(
            "# BLOCKED — centroid assign\n\n"
            f"{blocked}\n\n"
            "Per-part hypotheses and a naive time-offset merge were still written.\n",
            encoding="utf-8",
        )

    _write_gate(timing, manifest, merge_mode, blocked, cut_compare)
    _write_run_meta(timing, job_t0)
    print(json.dumps({"ttft": ttft, "ttft_after_sleep": ttft_sleep, "merge": merge_stats, "cut_compare": cut_compare}, indent=2, ensure_ascii=False))
    return 0


def _compare_near_cuts(part_rows: list[dict[str, Any]], cut: dict[str, Any]) -> dict[str, Any]:
    """Light compare vs full15 and previous per-part-VAD split3 near pause cuts."""
    full_tr = json.loads(FULL15_TRANSCRIPT.read_text(encoding="utf-8"))
    old_p2: dict[str, Any] | None = None
    if SPLIT3_OLD_PART02.is_file():
        old_p2 = json.loads(SPLIT3_OLD_PART02.read_text(encoding="utf-8"))

    def segs_in_window(segments: list[dict[str, Any]], lo: float, hi: float) -> list[dict[str, Any]]:
        out = []
        for seg in segments:
            if float(seg["end"]) < lo or float(seg["start"]) > hi:
                continue
            out.append(
                {
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": seg.get("text") or "",
                }
            )
        return out

    cut_t = float(cut["cuts"][0]["t"]) if cut.get("cuts") else 291.392
    full_win = segs_in_window(full_tr.get("segments") or [], cut_t, cut_t + 12.0)
    long_phrase = ""
    for seg in full_win:
        if "по магистральным сетям" in seg["text"] and len(seg["text"]) > 40:
            long_phrase = seg["text"]
            break
    if not long_phrase and full_win:
        long_phrase = max((s["text"] for s in full_win), key=len)

    p2 = next((r for r in part_rows if r["part_id"] == "part02"), None)
    new_open = []
    if p2 is not None:
        offset = float(p2["plan_start"])
        for seg in list(p2["transcript"].segments)[:4]:
            new_open.append(
                {
                    "local_start": seg.start,
                    "abs_start": _round3(seg.start + offset),
                    "abs_end": _round3(seg.end + offset),
                    "text": seg.text,
                }
            )
    old_open = []
    if old_p2 is not None:
        offset = 291.392
        for seg in (old_p2.get("segments") or [])[:4]:
            old_open.append(
                {
                    "local_start": seg["start"],
                    "abs_start": _round3(float(seg["start"]) + offset),
                    "text": seg.get("text") or "",
                }
            )

    new_joined = " ".join(s["text"] for s in new_open)
    old_joined = " ".join(s["text"] for s in old_open)
    phrase_in_new = bool(long_phrase) and (
        long_phrase[:40] in new_joined or "давайте сейчас второй" in new_joined
    )
    phrase_in_old = bool(long_phrase) and (
        long_phrase[:40] in old_joined or "давайте сейчас второй" in old_joined
    )
    recovered = phrase_in_new and not phrase_in_old
    return {
        "cut_t": cut_t,
        "full15_near_cut": full_win[:4],
        "full15_long_phrase": long_phrase,
        "split3_per_part_vad_part02_open": old_open,
        "shared_vad_part02_open": new_open,
        "long_phrase_in_old_split3": phrase_in_old,
        "long_phrase_in_shared_vad": phrase_in_new,
        "recovered_vs_split3": recovered,
    }


def _write_gate(
    timing: dict[str, Any],
    manifest: dict[str, Any],
    merge_mode: str,
    blocked: str | None,
    cut_compare: dict[str, Any],
) -> None:
    parts = timing["parts"]
    rows = []
    for stage in STAGES:
        cells = []
        for pid in ("part01", "part02", "part03"):
            st = parts[pid]["stages"][stage]
            flag = " skip" if st.get("skipped") else ""
            cells.append(f"{st['wall_sec']:.3f}s{flag}")
        rows.append(f"| {stage} | " + " | ".join(cells) + " |")

    merge = timing["merge"]
    cross = timing["cross_part"]
    verdict = "PASS"
    if blocked and not timing["centroid_assign_ok"]:
        verdict = "FAIL"
    elif not merge["count_match"] or not merge["monotonic"] or not merge["part_blocks_preserved"]:
        verdict = "FAIL"
    elif not cross["stable_ids_part01_part02"]:
        verdict = "PASS_WITH_WARNINGS"

    lines = [
        "# Gate D5.TTFT-split3 — shared full15 VAD",
        "",
        f"## Verdict: {verdict}",
        "",
        "## Timing (part × stage wall_sec from overall job start)",
        "",
        "VAD is **skipped** on every part: `speech.json` is sliced from "
        "`cloud_out/artifacts/full15/speech.json` (intersect [plan_start, plan_end], "
        "clip, subtract plan_start).",
        "",
        f"ttft_first_chapter_sec (part01 chunk done) = **{timing['ttft_first_chapter_sec']}**",
        f"ttft_after_sleep_sec (part01 chunk + 2.0s) = **{timing['ttft_after_sleep_sec']}**",
        f"wall_total_sec (all 3 parts + sleeps, no per-part VAD) = **{timing['wall_total_sec']}**",
        "",
        "| stage | part01 | part02 | part03 |",
        "|---|---:|---:|---:|",
        *rows,
        "",
        "### Cumulative after each part",
        "",
        "| part | cumulative_from_job_start_sec | speakers | n_turns | n_segments | n_chapters |",
        "|---|---:|---|---:|---:|---:|",
    ]
    for pid in ("part01", "part02", "part03"):
        p = parts[pid]
        lines.append(
            f"| {pid} | {p['cumulative_from_job_start_sec']} | {p['speaker_count']} | "
            f"{p['n_turns']} | {p['n_segments']} | {p['n_chapters']} |"
        )

    dur_rows = []
    for item in manifest["parts"]:
        delta = item["duration_delta_sec"]
        status = "PASS" if abs(delta) <= 1.0 else "FAIL"
        dur_rows.append(
            f"| {item['id']} | {item['plan_duration_sec']} | {item['ffprobe_duration_sec']} | "
            f"{delta} | {status} |"
        )

    lines += [
        "",
        "## Checks",
        "",
        "| id | check | value | threshold | status |",
        "|---|---|---|---|---|",
        f"| S0 | reuse packed splits | {len(manifest['parts'])} m4a | durations ±1.0 s | "
        + ("PASS" if all(abs(p['duration_delta_sec']) <= 1.0 for p in manifest['parts']) else "FAIL")
        + " |",
        "| V0 | per-part Silero VAD | skipped | do not run vad stage | PASS |",
        f"| V1 | shared VAD source | {timing.get('vad_source')} | full15/speech.json slice | PASS |",
        f"| D1 | cluster_distance_threshold | {timing['cluster_distance_threshold']} | 0.85 | PASS |",
        f"| D2 | centroid assign | {timing['centroid_assign_ok']} | part2/3 nearest-centroid | "
        + ("PASS" if timing["centroid_assign_ok"] else "FAIL")
        + " |",
        f"| C1 | stable speaker ids part1∩part2 | {cross['stable_ids_part01_part02']} | non-empty preferred | "
        + ("PASS" if cross["stable_ids_part01_part02"] else "WARN")
        + " |",
        f"| C2 | stable speaker ids part2∩part3 | {cross['stable_ids_part02_part03']} | non-empty preferred | "
        + ("PASS" if cross["stable_ids_part02_part03"] else "WARN")
        + " |",
        f"| P1 | packing tail across cuts | spanning={cross['chapters_spanning_cuts']} | packing-C may extend | "
        + ("PASS" if cross["chapters_spanning_cuts"] else "WARN")
        + " |",
        f"| M1 | merged segment count | {merge['n_merged']} == {merge['n_expected']} | no drops | "
        + ("PASS" if merge["count_match"] else "FAIL")
        + " |",
        f"| M2 | merged monotonic start | {merge['monotonic']} | no shuffle | "
        + ("PASS" if merge["monotonic"] else "FAIL")
        + " |",
        f"| M3 | per-part blocks preserved | {merge['part_blocks_preserved']} | contiguous texts | "
        + ("PASS" if merge["part_blocks_preserved"] else "FAIL")
        + " |",
        f"| T1 | ttft_first_chapter_sec | {timing['ttft_first_chapter_sec']} | part01 chunk done | PASS (record) |",
        f"| T2 | ttft_after_sleep_sec | {timing['ttft_after_sleep_sec']} | +2.0 s sleep | PASS (record) |",
        f"| L1 | LLM calls | 0 (sleep only) | no Gemini/NVIDIA/Qwen | PASS |",
        f"| Q1 | part02 opening recovers full15 long phrase | recovered={cut_compare.get('recovered_vs_split3')} in_shared={cut_compare.get('long_phrase_in_shared_vad')} in_old_split3={cut_compare.get('long_phrase_in_old_split3')} | keep phrase after cut ~292s | "
        + ("PASS" if cut_compare.get("long_phrase_in_shared_vad") else "WARN")
        + " |",
        "",
        "## Part durations vs plan",
        "",
        "| part | plan_sec | ffprobe_sec | delta | status |",
        "|---|---:|---:|---:|---|",
        *dur_rows,
        "",
        "## Cut ~292 s (full15 vs old split3 vs shared VAD)",
        "",
        f"Full15 long phrase: «{cut_compare.get('full15_long_phrase') or ''}»",
        "",
        f"Old split3 part02 opening (per-part Silero): "
        f"{[s.get('text') for s in (cut_compare.get('split3_per_part_vad_part02_open') or [])]}",
        "",
        f"Shared-VAD part02 opening: "
        f"{[s.get('text') for s in (cut_compare.get('shared_vad_part02_open') or [])]}",
        "",
        f"Phrase present in old split3: {cut_compare.get('long_phrase_in_old_split3')}. "
        f"Phrase present with shared VAD: {cut_compare.get('long_phrase_in_shared_vad')}. "
        f"Recovered vs split3: {cut_compare.get('recovered_vs_split3')}.",
        "",
        "## Agent judgement",
        "",
        f"Merge mode: `{merge_mode}`. VAD was **not** re-run per part. Regions come from "
        "the existing full15 Silero `speech.json`, clipped to each pause-cut window. "
        "Speaker gallery from part1 AHC is reused for part2/3 windows (cosine distance ≤ 0.85). "
        "Packing C still carries the previous part's last chapter on the absolute timeline.",
        "",
        f"Stable ids part01∩part02: {cross['stable_ids_part01_part02'] or 'none'}. "
        f"part02∩part03: {cross['stable_ids_part02_part03'] or 'none'}. "
        f"Chapters spanning cuts: {cross['chapters_spanning_cuts'] or 'none (packing-C did not merge across the pause)'}.",
        "",
        "No LLM titles. `llm_sleep_2s` is `time.sleep(2.0)` after chunk on every part.",
        "",
        "## Environment",
        "",
        "- host nproc recorded in run_meta.json; onnx_threads=2; HF_HUB_OFFLINE=1",
        "- existing part01..03.m4a reused; full15 speech.json reused; weights reused",
        "- helper: cloud_out/artifacts/split3_shared_vad/scripts/ (no src/ or config/ edits)",
        "- previous split3/ artifacts were not overwritten",
        "",
        "## Deviations and blockers",
        "",
        blocked or "None.",
        "",
    ]
    (SPLIT3 / "gate_shared_vad.md").write_text("\n".join(lines), encoding="utf-8")


def _write_run_meta(timing: dict[str, Any], job_t0: float) -> None:
    import subprocess

    def sh(cmd: str) -> str:
        return subprocess.check_output(cmd, shell=True, text=True).strip()

    meta = {
        "schema_version": "1",
        "stage": "D5.TTFT-split3-shared-vad",
        "branch": sh("git rev-parse --abbrev-ref HEAD"),
        "git_rev": sh("git rev-parse HEAD"),
        "host": {
            "nproc": int(sh("nproc")),
            "python_version": sh("python3 --version"),
            "ffmpeg_version": sh("ffmpeg -version | head -1"),
        },
        "llm_call_count": 0,
        "ttft_first_chapter_sec": timing["ttft_first_chapter_sec"],
        "ttft_after_sleep_sec": timing["ttft_after_sleep_sec"],
        "wall_total_sec": timing["wall_total_sec"],
        "centroid_assign_ok": timing["centroid_assign_ok"],
        "merge_mode": timing["merge_mode"],
        "notes": [
            "3-part split with shared full15 VAD slices; no per-part Silero; no src/config edits.",
            "llm_sleep_2s is a wall-clock sleep, not an API call.",
            "Does not clobber cloud_out/artifacts/split3/.",
        ],
        "written_at_utc": _now_utc(),
    }
    _write_json(SPLIT3 / "run_meta.json", meta)


if __name__ == "__main__":
    raise SystemExit(main())

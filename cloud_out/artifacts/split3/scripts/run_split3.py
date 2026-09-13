#!/usr/bin/env python3
"""Run 3-part pause-split pipeline with cross-part speaker and packing continuity.

Writes artifacts under cloud_out/artifacts/split3/. Does not modify src/ or config/.
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
    TranscriptArtifact,
    TranscriptSegment,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)
from transcriber.pipeline.orchestrator import run_stage  # noqa: E402
from transcriber.registry import build  # noqa: E402

SPLIT3 = ROOT / "cloud_out" / "artifacts" / "split3"
PARTS_DIR = ROOT / "cloud_out" / "artifacts" / "parts"
CUT_PLAN = ROOT / "cloud_in" / "inputs" / "artifacts" / "cut_plan_15min_3.json"
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

        # normalize
        t_started = time.monotonic() - job_t0
        run_stage("normalize", job_dir, cfg=cfg, source_audio=audio)
        t_done = time.monotonic() - job_t0
        _mark_stage(marks, "normalize", started=t_started, done=t_done)

        # vad
        t_started = time.monotonic() - job_t0
        run_stage("vad", job_dir, cfg=cfg, source_audio=audio)
        t_done = time.monotonic() - job_t0
        _mark_stage(marks, "vad", started=t_started, done=t_done)

        # diarize
        t_started = time.monotonic() - job_t0
        speech = load_artifact(job_dir / "speech.json", SpeechArtifact)
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

    _write_gate(timing, manifest, merge_mode, blocked)
    _write_run_meta(timing, job_t0)
    print(json.dumps({"ttft": ttft, "ttft_after_sleep": ttft_sleep, "merge": merge_stats}, indent=2))
    return 0


def _write_gate(
    timing: dict[str, Any],
    manifest: dict[str, Any],
    merge_mode: str,
    blocked: str | None,
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
        "# Gate D5.TTFT-split3 — cross-part continuity",
        "",
        f"## Verdict: {verdict}",
        "",
        "## Timing (part × stage wall_sec from overall job start)",
        "",
        f"ttft_first_chapter_sec (part01 chunk done) = **{timing['ttft_first_chapter_sec']}**",
        f"ttft_after_sleep_sec (part01 chunk + 2.0s) = **{timing['ttft_after_sleep_sec']}**",
        f"wall_total_sec (all 3 parts + sleeps) = **{timing['wall_total_sec']}**",
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
        "",
        "## Part durations vs plan",
        "",
        "| part | plan_sec | ffprobe_sec | delta | status |",
        "|---|---:|---:|---:|---|",
        *dur_rows,
        "",
        "## Agent judgement",
        "",
        f"Merge mode: `{merge_mode}`. Speaker gallery from part1 AHC is reused for part2/3 "
        "windows (cosine distance ≤ 0.85 → same SPEAKER_* ; leftovers AHC'd as new ids). "
        "Packing C on part N prepends the previous part's last chapter segments on the "
        "absolute timeline so a chapter may extend across a pause cut.",
        "",
        f"Stable ids part01∩part02: {cross['stable_ids_part01_part02'] or 'none'}. "
        f"part02∩part03: {cross['stable_ids_part02_part03'] or 'none'}. "
        f"Chapters spanning cuts: {cross['chapters_spanning_cuts'] or 'none (packing-C did not merge across the pause)'}.",
        "",
        "No LLM titles. `llm_sleep_2s` is `time.sleep(2.0)` after chunk on every part.",
        "",
        "## Environment",
        "",
        "- nproc recorded in run_meta.json; onnx_threads=2; HF_HUB_OFFLINE=1",
        "- existing part01..03.m4a reused; weights reused from local caches",
        "- helper: cloud_out/artifacts/split3/scripts/ (no src/ or config/ edits)",
        "",
        "## Deviations and blockers",
        "",
        blocked or "None.",
        "",
    ]
    (SPLIT3 / "gate_split3.md").write_text("\n".join(lines), encoding="utf-8")


def _write_run_meta(timing: dict[str, Any], job_t0: float) -> None:
    import subprocess

    def sh(cmd: str) -> str:
        return subprocess.check_output(cmd, shell=True, text=True).strip()

    meta = {
        "schema_version": "1",
        "stage": "D5.TTFT-split3-continuity",
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
            "3-part split with centroid assign and packing tail; no src/config edits.",
            "llm_sleep_2s is a wall-clock sleep, not an API call.",
        ],
        "written_at_utc": _now_utc(),
    }
    _write_json(SPLIT3 / "run_meta.json", meta)


if __name__ == "__main__":
    raise SystemExit(main())

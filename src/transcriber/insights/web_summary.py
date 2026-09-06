"""Онлайн-саммари для демо-UI: один отчётный вызов LLM, без extract по главам."""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from time import monotonic

from pydantic import BaseModel, ConfigDict, ValidationError

from transcriber.config.schema import AppConfig
from transcriber.correction.apply_edits import STALE_MARKER_NAME
from transcriber.export.markdown import MarkdownExporter
from transcriber.insights.report import ReportPayload, _chapter_index, _insights_for_prompt
from transcriber.llm.factory import complete_json, make_client
from transcriber.llm.prompts import load_prompt, load_schema, render_prompt
from transcriber.models.artifacts import (
    ChaptersArtifact,
    InsightChapter,
    InsightsArtifact,
    InsightSource,
    KeyPoint,
    ReportArtifact,
    ReportChapterRef,
    ReportKeyMoment,
    ReportSpeakerItem,
    TranscriptArtifact,
    TranscriptSegment,
    dump_artifact,
    load_artifact,
)

logger = logging.getLogger(__name__)

USAGE_NAME = "summary_usage.json"
_DIGEST_CHARS = 700
_locks_guard = threading.Lock()
_job_locks: dict[str, threading.Lock] = {}


class SummaryBudgetError(RuntimeError):
    """Лимит вызовов саммари исчерпан; сообщение можно показать пользователю."""


class SummaryUsage(BaseModel):
    """Счётчик LLM-вызовов кнопки саммари на одну задачу."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    calls: int = 0


def job_lock(job_id: str) -> threading.Lock:
    """Замок на задачу, чтобы двойной клик не съел бюджет параллельно."""
    with _locks_guard:
        lock = _job_locks.get(job_id)
        if lock is None:
            lock = threading.Lock()
            _job_locks[job_id] = lock
        return lock


def load_usage(job_dir: Path) -> SummaryUsage:
    """Читает sidecar; битый файл считается нулевым счётчиком."""
    path = job_dir / USAGE_NAME
    if not path.is_file():
        return SummaryUsage()
    try:
        return load_artifact(path, SummaryUsage)
    except Exception:
        logger.warning("invalid summary_usage.json")
        return SummaryUsage()


def remaining_calls(job_dir: Path, max_calls: int) -> int:
    """Сколько вызовов саммари ещё можно сделать."""
    if max_calls <= 0:
        return 0
    used = load_usage(job_dir).calls
    return max(0, max_calls - used)


def _save_usage(job_dir: Path, usage: SummaryUsage) -> None:
    dump_artifact(usage, job_dir / USAGE_NAME)


def _chapter_segments(
    chapter_source_ids: list[str],
    by_id: dict[str, TranscriptSegment],
) -> list[TranscriptSegment]:
    return [by_id[sid] for sid in chapter_source_ids if sid in by_id]


def _digest_insights(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
) -> InsightsArtifact:
    by_id = {seg.id: seg for seg in transcript.segments}
    packed: list[InsightChapter] = []
    for chapter in chapters.chapters:
        segments = _chapter_segments(chapter.source_ids, by_id)
        lines: list[str] = []
        sources: list[InsightSource] = []
        used = 0
        for seg in segments:
            text = seg.text.strip()
            if not text:
                continue
            piece = f"{seg.speaker}: {text}"
            if used and used + len(piece) + 1 > _DIGEST_CHARS:
                break
            lines.append(piece)
            sources.append(
                InsightSource(
                    segment_id=seg.id,
                    start=seg.start,
                    end=seg.end,
                    speaker=seg.speaker,
                )
            )
            used += len(piece) + 1
        if not sources:
            continue
        packed.append(
            InsightChapter(
                id=chapter.id,
                start=chapter.start,
                end=chapter.end,
                key_points=[KeyPoint(text="\n".join(lines), src=sources[:8])],
            )
        )
    return InsightsArtifact(
        schema_version="1",
        job_id=chapters.job_id,
        provider="digest",
        model="none",
        prompt_id="web_summary/digest",
        chapters=packed,
        llm_calls=0,
        runtime_sec=0.0,
    )


def _hydrate_moments(
    payload: ReportPayload,
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
) -> list[ReportKeyMoment]:
    chapter_ids = {chapter.id: set(chapter.source_ids) for chapter in chapters.chapters}
    by_id = {seg.id: seg for seg in transcript.segments}
    moments: list[ReportKeyMoment] = []
    seen: set[tuple[str, str]] = set()
    for item in payload.key_moments:
        key = (item.chapter_id, item.segment_id)
        if key in seen:
            continue
        allowed = chapter_ids.get(item.chapter_id)
        if allowed is None or item.segment_id not in allowed:
            continue
        seg = by_id.get(item.segment_id)
        if seg is None:
            continue
        seen.add(key)
        moments.append(
            ReportKeyMoment(
                text=item.text,
                start=seg.start,
                end=seg.end,
                speaker=seg.speaker,
                chapter_id=item.chapter_id,
            )
        )
    return moments


def run_web_summary(job_dir: Path, cfg: AppConfig) -> ReportArtifact:
    """Собирает report.json / report.md. Считает только вызовы кнопки саммари."""
    with job_lock(job_dir.name):
        return _run_web_summary_locked(job_dir, cfg)


def _run_web_summary_locked(job_dir: Path, cfg: AppConfig) -> ReportArtifact:
    """Собирает report.json / report.md. Считает только вызовы кнопки саммари."""
    max_calls = cfg.ui.summary_max_calls
    if max_calls <= 0:
        raise SummaryBudgetError("Саммари по выбранному шаблону пока недоступно.")
    usage = load_usage(job_dir)
    if usage.calls >= max_calls:
        raise SummaryBudgetError("Лимит саммари для этой задачи исчерпан.")

    transcript = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
    chapters = load_artifact(job_dir / "chapters.json", ChaptersArtifact)
    insights = _digest_insights(chapters, transcript)
    if not insights.chapters:
        raise RuntimeError("no chapter text for summary")

    task = cfg.llm.tasks.meeting_insights.report
    prompt = render_prompt(
        load_prompt(task.prompt),
        {
            "chapter_index": _chapter_index(chapters),
            "insights_json": _insights_for_prompt(insights),
        },
    )
    schema = load_schema(task.schema_)
    client = make_client(cfg.llm)
    started = monotonic()
    payload: ReportPayload | None = None
    response = None
    attempts = min(2, max_calls - usage.calls)
    last_error = "invalid summary response"
    for _ in range(max(1, attempts)):
        response = complete_json(
            client,
            prompt=prompt,
            prompt_id="meeting_insights/v1_report",
            schema=schema,
            cfg=cfg.llm,
            task=task,
        )
        usage.calls += 1
        _save_usage(job_dir, usage)
        try:
            payload = ReportPayload.model_validate(json.loads(response.text))
            break
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)
            payload = None
            if usage.calls >= max_calls:
                break
    if payload is None or response is None:
        raise RuntimeError(last_error)

    moments = _hydrate_moments(payload, chapters, transcript)
    speech_by_speaker: dict[str, float] = {}
    for segment in transcript.segments:
        speech_by_speaker[segment.speaker] = (
            speech_by_speaker.get(segment.speaker, 0.0) + segment.end - segment.start
        )
    report = ReportArtifact(
        schema_version="1",
        job_id=chapters.job_id,
        summary=payload.summary,
        key_moments=moments,
        speakers=[
            ReportSpeakerItem(
                id=speaker,
                label=None,
                speech_sec=round(duration, 3),
            )
            for speaker, duration in sorted(speech_by_speaker.items())
        ],
        chapters=[
            ReportChapterRef(
                id=chapter.id,
                title=chapter.title,
                start=chapter.start,
                end=chapter.end,
            )
            for chapter in chapters.chapters
        ],
        provider=response.provider,
        model=response.model,
        llm_calls=usage.calls,
        draft_warning=cfg.app.profile == "demo",
        runtime_sec=round(monotonic() - started, 3),
    )
    dump_artifact(report, job_dir / "report.json")
    MarkdownExporter().export(report, job_dir / "report.md")
    (job_dir / STALE_MARKER_NAME).unlink(missing_ok=True)
    logger.info(
        "web summary written job_id=%s calls=%s remaining=%s",
        chapters.job_id,
        usage.calls,
        max(0, max_calls - usage.calls),
    )
    return report

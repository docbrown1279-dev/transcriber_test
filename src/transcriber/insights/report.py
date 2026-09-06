"""Meeting report generation and deterministic hydration."""

from __future__ import annotations

import json
from time import monotonic

from pydantic import BaseModel, ConfigDict, ValidationError

from transcriber.config.schema import AppConfig
from transcriber.llm.base import LlmClient
from transcriber.llm.factory import complete_json
from transcriber.llm.prompts import load_prompt, load_schema, render_prompt
from transcriber.models.artifacts import (
    ChaptersArtifact,
    InsightSource,
    InsightsArtifact,
    ReportArtifact,
    ReportChapterRef,
    ReportKeyMoment,
    ReportSpeakerItem,
    TranscriptArtifact,
)


class ReportMomentPayload(BaseModel):
    """Ключевой момент до гидратации времени и спикера."""

    model_config = ConfigDict(extra="forbid")

    text: str
    chapter_id: str
    segment_id: str


class ReportPayload(BaseModel):
    """Ответ модели для сводного протокола."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    key_moments: list[ReportMomentPayload]


def _chapter_index(chapters: ChaptersArtifact) -> str:
    return "\n".join(
        f"{chapter.id} | {chapter.start:.3f}-{chapter.end:.3f} | {chapter.title}"
        for chapter in chapters.chapters
    )


def _insights_for_prompt(insights: InsightsArtifact) -> str:
    return json.dumps(
        {"chapters": [chapter.model_dump(mode="json") for chapter in insights.chapters]},
        ensure_ascii=False,
        sort_keys=True,
    )


def generate_report(
    insights: InsightsArtifact,
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    client: LlmClient,
    cfg: AppConfig,
) -> ReportArtifact:
    """Создаёт один сводный протокол и копирует временные метки источников."""
    if len({insights.job_id, chapters.job_id, transcript.job_id}) != 1:
        raise ValueError("Transcript, chapters, and insights job_id values differ")
    if insights.llm_calls >= cfg.llm.max_calls_per_job:
        raise RuntimeError("LLM call budget exhausted before report generation")

    started = monotonic()
    task = cfg.llm.tasks.meeting_insights.report
    prompt = render_prompt(
        load_prompt(task.prompt),
        {
            "chapter_index": _chapter_index(chapters),
            "insights_json": _insights_for_prompt(insights),
        },
    )
    response = complete_json(
        client,
        prompt=prompt,
        prompt_id="meeting_insights/v1_report",
        schema=load_schema(task.schema_),
        cfg=cfg.llm,
        task=task,
    )
    try:
        payload = ReportPayload.model_validate(json.loads(response.text))
    except (json.JSONDecodeError, ValidationError) as exc:
        raise RuntimeError(f"Invalid report response: {exc}") from exc

    allowed: dict[tuple[str, str], InsightSource] = {}
    for chapter in insights.chapters:
        for item in chapter.key_points + chapter.actions + chapter.open_questions:
            for source in item.src:
                allowed[(chapter.id, source.segment_id)] = source

    moments: list[ReportKeyMoment] = []
    for item in payload.key_moments:
        source = allowed.get((item.chapter_id, item.segment_id))
        if source is None:
            raise ValueError(
                "Report references source absent from insights: "
                f"{item.chapter_id}/{item.segment_id}"
            )
        moments.append(
            ReportKeyMoment(
                text=item.text,
                start=source.start,
                end=source.end,
                speaker=source.speaker,
                chapter_id=item.chapter_id,
            )
        )

    speech_by_speaker: dict[str, float] = {}
    for segment in transcript.segments:
        speech_by_speaker[segment.speaker] = (
            speech_by_speaker.get(segment.speaker, 0.0) + segment.end - segment.start
        )
    return ReportArtifact(
        schema_version="1",
        job_id=insights.job_id,
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
        llm_calls=1,
        draft_warning=cfg.app.profile == "demo",
        runtime_sec=round(monotonic() - started, 3),
    )

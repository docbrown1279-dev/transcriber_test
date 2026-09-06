"""Per-chapter insight extraction with transcript-source hydration."""

from __future__ import annotations

import json
import re
from time import monotonic

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from transcriber.config.schema import AppConfig
from transcriber.llm.base import LlmClient, LlmResponse
from transcriber.llm.factory import complete_json
from transcriber.llm.prompts import load_prompt, load_schema, render_prompt
from transcriber.models.artifacts import (
    AsrNote,
    ChapterItem,
    ChaptersArtifact,
    InsightChapter,
    InsightsArtifact,
    InsightSource,
    KeyPoint,
    TranscriptArtifact,
    TranscriptSegment,
)


class ExtractItemPayload(BaseModel):
    """Элемент ответа модели до привязки к временным меткам."""

    model_config = ConfigDict(extra="forbid")

    text: str
    segment_ids: list[str] = Field(min_length=1)


class AsrNotePayload(BaseModel):
    """Заметка о возможной ошибке распознавания."""

    model_config = ConfigDict(extra="forbid")

    text: str


class ExtractPayload(BaseModel):
    """Ответ модели для одной главы до гидратации."""

    model_config = ConfigDict(extra="forbid")

    key_points: list[ExtractItemPayload]
    actions: list[ExtractItemPayload]
    open_questions: list[ExtractItemPayload]
    asr_notes: list[AsrNotePayload]


def _chapter_sources(
    chapter: ChapterItem,
    transcript: TranscriptArtifact,
) -> list[TranscriptSegment]:
    by_id = {segment.id: segment for segment in transcript.segments}
    try:
        return [by_id[source_id] for source_id in chapter.source_ids]
    except KeyError as exc:
        raise ValueError(
            f"Chapter {chapter.id} references unknown transcript segment {exc.args[0]}"
        ) from exc


def _render_chapter_prompt(
    template: str,
    chapter: ChapterItem,
    segments: list[TranscriptSegment],
) -> str:
    chapter_text = "\n".join(
        f"{segment.speaker}: {segment.text.strip()}"
        for segment in segments
        if segment.text.strip()
    )
    catalog = "\n".join(
        f"{segment.id} | {segment.start:.3f}-{segment.end:.3f} | {segment.speaker}"
        for segment in segments
    )
    return render_prompt(
        template,
        {
            "chapter_id": chapter.id,
            "title": chapter.title,
            "start": f"{chapter.start:.3f}",
            "end": f"{chapter.end:.3f}",
            "chapter_text": chapter_text,
            "src_catalog": catalog,
        },
    )


def hydrate_items(
    items: list[ExtractItemPayload],
    chapter: ChapterItem,
    transcript: TranscriptArtifact,
    *,
    drop_unknown: bool,
) -> tuple[list[KeyPoint], list[str]]:
    """Привязывает разрешённые segment_id к меткам стенограммы."""
    by_id = {segment.id: segment for segment in transcript.segments}
    allowed = set(chapter.source_ids)
    hydrated: list[KeyPoint] = []
    unknown: list[str] = []
    for item in items:
        invalid = [
            segment_id
            for segment_id in item.segment_ids
            if segment_id not in by_id or segment_id not in allowed
        ]
        if invalid:
            unknown.extend(invalid)
            if drop_unknown:
                continue
            continue
        hydrated.append(
            KeyPoint(
                text=item.text,
                src=[
                    InsightSource(
                        segment_id=segment_id,
                        start=by_id[segment_id].start,
                        end=by_id[segment_id].end,
                        speaker=by_id[segment_id].speaker,
                    )
                    for segment_id in item.segment_ids
                ],
            )
        )
    return hydrated, unknown


def _chapter_plain_text(chapter: ChapterItem, transcript: TranscriptArtifact) -> str:
    by_id = {segment.id: segment for segment in transcript.segments}
    return " ".join(
        by_id[source_id].text
        for source_id in chapter.source_ids
        if source_id in by_id
    )


def _digit_groups_verified(text: str, chapter_text: str) -> bool:
    return all(digits in chapter_text for digits in re.findall(r"\d+", text))


def filter_digit_verified_key_points(
    key_points: list[KeyPoint],
    chapter_text: str,
) -> list[KeyPoint]:
    """Удаляет key_points с цифрами, которых нет в исходном тексте главы."""
    return [
        key_point
        for key_point in key_points
        if _digit_groups_verified(key_point.text, chapter_text)
    ]


def extract_insights(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    client: LlmClient,
    cfg: AppConfig,
) -> InsightsArtifact:
    """Извлекает факты по главам и копирует ссылки из стенограммы."""
    if chapters.job_id != transcript.job_id:
        raise ValueError("Transcript and chapters job_id values differ")

    started = monotonic()
    task = cfg.llm.tasks.meeting_insights.extract
    template = load_prompt(task.prompt)
    schema = load_schema(task.schema_)
    output: list[InsightChapter] = []
    calls = 0
    last_response: LlmResponse | None = None

    for chapter in chapters.chapters:
        prompt = _render_chapter_prompt(
            template,
            chapter,
            _chapter_sources(chapter, transcript),
        )
        payload: ExtractPayload | None = None
        has_unknown = False
        for attempt in range(2):
            if calls >= cfg.llm.max_calls_per_job:
                raise RuntimeError(
                    f"LLM call budget exhausted before insights for chapter {chapter.id}"
                )
            response = complete_json(
                client,
                prompt=prompt,
                prompt_id="meeting_insights/v1_extract",
                schema=schema,
                cfg=cfg.llm,
                task=task,
            )
            calls += 1
            last_response = response
            try:
                payload = ExtractPayload.model_validate(json.loads(response.text))
            except (json.JSONDecodeError, ValidationError) as exc:
                if attempt == 0:
                    continue
                raise RuntimeError(
                    f"Invalid extract response for chapter {chapter.id}: {exc}"
                ) from exc

            all_items = payload.key_points + payload.actions + payload.open_questions
            _, unknown = hydrate_items(
                all_items,
                chapter,
                transcript,
                drop_unknown=False,
            )
            has_unknown = bool(unknown)
            if not has_unknown or attempt == 1:
                break

        if payload is None:
            raise RuntimeError(f"No valid extract response for chapter {chapter.id}")
        drop_unknown = has_unknown
        key_points, _ = hydrate_items(
            payload.key_points, chapter, transcript, drop_unknown=drop_unknown
        )
        chapter_text = _chapter_plain_text(chapter, transcript)
        key_points = filter_digit_verified_key_points(key_points, chapter_text)
        actions, _ = hydrate_items(
            payload.actions, chapter, transcript, drop_unknown=drop_unknown
        )
        questions, _ = hydrate_items(
            payload.open_questions, chapter, transcript, drop_unknown=drop_unknown
        )
        output.append(
            InsightChapter(
                id=chapter.id,
                start=chapter.start,
                end=chapter.end,
                key_points=key_points,
                actions=actions,
                open_questions=questions,
                asr_notes=[AsrNote(text=note.text) for note in payload.asr_notes],
            )
        )

    if last_response is None:
        backend = cfg.llm.active_backend
        provider = cfg.llm.backend
        model = backend.model
    else:
        provider = last_response.provider
        model = last_response.model
    return InsightsArtifact(
        schema_version="1",
        job_id=chapters.job_id,
        provider=provider,
        model=model,
        prompt_id="meeting_insights/v1_extract",
        chapters=output,
        llm_calls=calls,
        runtime_sec=round(monotonic() - started, 3),
    )

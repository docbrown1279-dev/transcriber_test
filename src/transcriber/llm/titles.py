"""Chapter-title generation and validation."""

from __future__ import annotations

import json
from time import monotonic

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from transcriber.config.schema import LlmConfig, LlmTaskConfig
from transcriber.llm.base import LlmClient
from transcriber.llm.factory import complete_json
from transcriber.llm.prompts import load_prompt, load_schema
from transcriber.models.artifacts import ChapterItem, ChaptersArtifact, TranscriptArtifact

STAMP_PREFIXES = (
    "обсуждение",
    "обсудили",
    "говорили о",
    "совещание по",
    "разговор о",
)

BATCH_PROMPT = "prompts/chapter_titles/v1_batch.md"
BATCH_SCHEMA = "schemas/chapter_titles_batch.json"


class TitlePayload(BaseModel):
    """Минимальная часть JSON-ответа, используемая артефактом глав."""

    model_config = ConfigDict(extra="ignore")

    title: str


class BatchTitleItem(BaseModel):
    """One titled chapter in a batch response."""

    model_config = ConfigDict(extra="ignore")

    id: str
    title: str


class BatchTitlesPayload(BaseModel):
    """JSON response for multi-chapter title generation."""

    model_config = ConfigDict(extra="ignore")

    titles: list[BatchTitleItem] = Field(min_length=1)


def title_validation_error(
    title: str,
    max_words: int,
    existing_titles: set[str] | None = None,
) -> str | None:
    """Возвращает причину нарушения правил заголовка либо None."""
    normalized = " ".join(title.split())
    if not normalized:
        return "title is empty"
    if len(normalized.split()) > max_words:
        return f"title exceeds {max_words} words"
    folded = normalized.casefold()
    if any(folded.startswith(prefix) for prefix in STAMP_PREFIXES):
        return "title starts with a forbidden stamp phrase"
    if existing_titles is not None and folded in existing_titles:
        return "title duplicates another chapter"
    return None


def chapter_text(chapter_source_ids: list[str], transcript: TranscriptArtifact) -> str:
    """Join non-empty speaker-prefixed lines for a chapter."""
    by_id = {segment.id: segment for segment in transcript.segments}
    lines: list[str] = []
    for source_id in chapter_source_ids:
        if source_id not in by_id:
            raise ValueError(f"Chapter references unknown transcript segment: {source_id}")
        segment = by_id[source_id]
        if segment.text.strip():
            lines.append(f"{segment.speaker}: {segment.text.strip()}")
    return "\n".join(lines)


def title_one_chapter(
    chapter: ChapterItem,
    transcript: TranscriptArtifact,
    client: LlmClient,
    cfg: LlmConfig,
    *,
    used_titles: set[str] | None = None,
    calls_so_far: int = 0,
) -> tuple[str, int]:
    """Generate a validated title for one chapter; returns (title, calls_used)."""
    task = cfg.tasks.chapter_titles
    prompt_template = load_prompt("prompts/chapter_titles/v1.md")
    response_schema = load_schema("schemas/chapter_title.json")
    text = chapter_text(chapter.source_ids, transcript)
    if not text:
        raise ValueError(f"Chapter {chapter.id} has no non-empty source text")
    prompt = f"{prompt_template}\n\nChapter text:\n{text}"
    used = used_titles if used_titles is not None else set()
    calls = 0
    last_error = "no response"
    single_task = LlmTaskConfig.model_validate(
        {
            "prompt": "prompts/chapter_titles/v1.md",
            "schema": "schemas/chapter_title.json",
            "max_tokens": task.max_tokens,
            "temperature": task.temperature,
            "response_format": task.response_format,
        }
    )
    for _attempt in range(cfg.title_max_attempts):
        if calls_so_far + calls >= cfg.max_calls_per_job:
            raise RuntimeError(
                f"LLM call budget exhausted before title for chapter {chapter.id}"
            )
        response = complete_json(
            client,
            prompt=prompt,
            prompt_id="chapter_titles/v1",
            schema=response_schema,
            cfg=cfg,
            task=single_task,
        )
        calls += 1
        try:
            payload = TitlePayload.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"invalid JSON response: {exc}"
            continue
        title = " ".join(payload.title.split())
        validation_error = title_validation_error(title, cfg.title_max_words, used)
        if validation_error is not None:
            last_error = validation_error
            continue
        return title, calls
    raise RuntimeError(f"Title generation failed for {chapter.id}: {last_error}")


def apply_titles_sequential(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    client: LlmClient,
    cfg: LlmConfig,
) -> tuple[ChaptersArtifact, int]:
    """One LLM call per chapter (baseline / mode B single)."""
    started = monotonic()
    generated = chapters.model_copy(deep=True)
    used_titles: set[str] = set()
    calls = 0
    for chapter in generated.chapters:
        title, used = title_one_chapter(
            chapter,
            transcript,
            client,
            cfg,
            used_titles=used_titles,
            calls_so_far=calls,
        )
        calls += used
        chapter.title = title
        used_titles.add(title.casefold())
    generated.runtime_sec = round(generated.runtime_sec + monotonic() - started, 3)
    return generated, calls


def apply_titles_batch(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    client: LlmClient,
    cfg: LlmConfig,
) -> tuple[ChaptersArtifact, int]:
    """One (or few) LLM call(s) for all chapter titles; fallback per chapter on failure."""
    started = monotonic()
    if not chapters.chapters:
        return chapters.model_copy(deep=True), 0

    task = cfg.tasks.chapter_titles
    batch_task = LlmTaskConfig.model_validate(
        {
            "prompt": BATCH_PROMPT,
            "schema": BATCH_SCHEMA,
            "max_tokens": max(task.max_tokens or 1024, 2048),
            "temperature": task.temperature,
            "response_format": task.response_format,
        }
    )
    prompt_template = load_prompt(BATCH_PROMPT)
    response_schema = load_schema(BATCH_SCHEMA)
    blocks: list[str] = []
    for chapter in chapters.chapters:
        text = chapter_text(chapter.source_ids, transcript)
        if not text:
            raise ValueError(f"Chapter {chapter.id} has no non-empty source text")
        blocks.append(f"### {chapter.id}\n{text}")
    prompt = (
        f"{prompt_template}\n\nChapters ({len(blocks)}):\n\n" + "\n\n".join(blocks)
    )

    generated = chapters.model_copy(deep=True)
    calls = 0
    last_error = "no response"
    for _attempt in range(cfg.title_max_attempts):
        if calls >= cfg.max_calls_per_job:
            break
        response = complete_json(
            client,
            prompt=prompt,
            prompt_id="chapter_titles/v1_batch",
            schema=response_schema,
            cfg=cfg,
            task=batch_task,
        )
        calls += 1
        try:
            payload = BatchTitlesPayload.model_validate(json.loads(response.text))
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = f"invalid JSON response: {exc}"
            continue
        by_id = {item.id: item.title for item in payload.titles}
        used: set[str] = set()
        ok = True
        pending: dict[str, str] = {}
        for chapter in generated.chapters:
            raw = by_id.get(chapter.id)
            if raw is None:
                ok = False
                last_error = f"missing title for {chapter.id}"
                break
            title = " ".join(raw.split())
            err = title_validation_error(title, cfg.title_max_words, used)
            if err is not None:
                ok = False
                last_error = f"{chapter.id}: {err}"
                break
            pending[chapter.id] = title
            used.add(title.casefold())
        if not ok:
            continue
        for chapter in generated.chapters:
            chapter.title = pending[chapter.id]
        generated.runtime_sec = round(generated.runtime_sec + monotonic() - started, 3)
        return generated, calls

    # Batch attempts failed validation/parse; finish with per-chapter calls.
    _ = last_error
    used_titles = {c.title.casefold() for c in generated.chapters if c.title.strip()}
    for chapter in generated.chapters:
        if chapter.title.strip():
            continue
        title, used = title_one_chapter(
            chapter,
            transcript,
            client,
            cfg,
            used_titles=used_titles,
            calls_so_far=calls,
        )
        calls += used
        chapter.title = title
        used_titles.add(title.casefold())
    generated.runtime_sec = round(generated.runtime_sec + monotonic() - started, 3)
    return generated, calls


def apply_titles(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    client: LlmClient,
    cfg: LlmConfig,
) -> tuple[ChaptersArtifact, int]:
    """Dispatch sequential vs batch from ``cfg.titles_mode``."""
    if cfg.titles_mode == "batch":
        return apply_titles_batch(chapters, transcript, client, cfg)
    return apply_titles_sequential(chapters, transcript, client, cfg)

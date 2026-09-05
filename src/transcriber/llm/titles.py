"""Chapter-title generation and validation."""

from __future__ import annotations

import json
from time import monotonic

from pydantic import BaseModel, ConfigDict, ValidationError

from transcriber.config.schema import LlmConfig
from transcriber.llm.base import LlmClient
from transcriber.llm.prompts import load_prompt
from transcriber.models.artifacts import ChaptersArtifact, TranscriptArtifact

STAMP_PREFIXES = (
    "обсуждение",
    "обсудили",
    "говорили о",
    "совещание по",
    "разговор о",
)


class TitlePayload(BaseModel):
    """Минимальная часть JSON-ответа, используемая артефактом глав."""

    model_config = ConfigDict(extra="ignore")

    title: str


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


def _chapter_text(chapter_source_ids: list[str], transcript: TranscriptArtifact) -> str:
    by_id = {segment.id: segment for segment in transcript.segments}
    lines: list[str] = []
    for source_id in chapter_source_ids:
        if source_id not in by_id:
            raise ValueError(f"Chapter references unknown transcript segment: {source_id}")
        segment = by_id[source_id]
        if segment.text.strip():
            lines.append(f"{segment.speaker}: {segment.text.strip()}")
    return "\n".join(lines)


def apply_titles(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    client: LlmClient,
    cfg: LlmConfig,
) -> tuple[ChaptersArtifact, int]:
    """Генерирует и проверяет заголовок каждой главы с ограниченным повтором."""
    if cfg.max_calls_per_job is None:
        raise ValueError("llm.max_calls_per_job must be configured")
    if cfg.temperature is None:
        raise ValueError("llm.temperature must be configured")

    started = monotonic()
    prompt_template = load_prompt(cfg.prompts.title)
    generated = chapters.model_copy(deep=True)
    used_titles: set[str] = set()
    calls = 0

    for chapter in generated.chapters:
        chapter_text = _chapter_text(chapter.source_ids, transcript)
        if not chapter_text:
            raise ValueError(f"Chapter {chapter.id} has no non-empty source text")
        prompt = f"{prompt_template}\n\nChapter text:\n{chapter_text}"
        last_error = "no response"
        for _attempt in range(cfg.title_max_attempts):
            if calls >= cfg.max_calls_per_job:
                raise RuntimeError(
                    f"Gemini call budget exhausted before title for chapter {chapter.id}"
                )
            response = client.complete(
                prompt,
                max_tokens=cfg.title_max_tokens,
                temperature=cfg.temperature,
            )
            calls += 1
            try:
                payload = TitlePayload.model_validate(json.loads(response.text))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = f"invalid JSON response: {exc}"
                continue
            title = " ".join(payload.title.split())
            validation_error = title_validation_error(title, cfg.title_max_words, used_titles)
            if validation_error is not None:
                last_error = validation_error
                continue
            chapter.title = title
            used_titles.add(title.casefold())
            break
        else:
            raise RuntimeError(f"Title generation failed for {chapter.id}: {last_error}")

    generated.runtime_sec = round(generated.runtime_sec + monotonic() - started, 3)
    return generated, calls

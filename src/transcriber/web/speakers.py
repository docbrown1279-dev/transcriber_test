"""Человеческие имена спикеров (sidecar speakers.json, id диаризации не меняются)."""

from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from transcriber.models.artifacts import TranscriptArtifact, dump_artifact, load_artifact

logger = logging.getLogger(__name__)

SPEAKERS_NAME = "speakers.json"
_ALIAS_MAX = 80


class SpeakerAliases(BaseModel):
    """Отображение SPEAKER_00 → «Иван» для UI."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    aliases: dict[str, str] = Field(default_factory=dict)


def speaker_ids(transcript: TranscriptArtifact) -> list[str]:
    """Уникальные id спикеров в порядке появления."""
    seen: set[str] = set()
    ordered: list[str] = []
    for seg in transcript.segments:
        if seg.speaker not in seen:
            seen.add(seg.speaker)
            ordered.append(seg.speaker)
    return ordered


def load_aliases(job_dir: Path) -> dict[str, str]:
    """Читает sidecar; битый файл игнорируется."""
    path = job_dir / SPEAKERS_NAME
    if not path.is_file():
        return {}
    try:
        payload = load_artifact(path, SpeakerAliases)
    except Exception:
        logger.warning("invalid speakers.json")
        return {}
    return {key: value.strip() for key, value in payload.aliases.items() if value.strip()}


def save_aliases(job_dir: Path, aliases: dict[str, str], known_ids: list[str]) -> dict[str, str]:
    """Пишет только известные id, обрезает имена."""
    known = set(known_ids)
    cleaned: dict[str, str] = {}
    for key, raw in aliases.items():
        if key not in known:
            continue
        name = " ".join(raw.split())[:_ALIAS_MAX]
        if name:
            cleaned[key] = name
    dump_artifact(SpeakerAliases(aliases=cleaned), job_dir / SPEAKERS_NAME)
    return cleaned


def clear_aliases(job_dir: Path) -> None:
    """Удаляет человеческие имена; id диаризации живут в транскрипте."""
    path = job_dir / SPEAKERS_NAME
    path.unlink(missing_ok=True)


def speech_seconds(transcript: TranscriptArtifact) -> dict[str, float]:
    """Суммарная длительность речи по id спикера."""
    totals: dict[str, float] = {}
    for seg in transcript.segments:
        totals[seg.speaker] = totals.get(seg.speaker, 0.0) + (seg.end - seg.start)
    return totals


def display_name(speaker_id: str, aliases: dict[str, str]) -> str:
    """Человеческое имя плюс id кластера, чтобы переименование не прятало диаризацию."""
    alias = aliases.get(speaker_id)
    if alias:
        return f"{alias} · {speaker_id}"
    return speaker_id

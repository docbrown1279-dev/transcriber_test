"""Определение стадий конвейера и графа их зависимостей."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from transcriber.config.schema import AppConfig
from transcriber.errors import StageNotImplementedError
from transcriber.models.artifacts import (
    AudioArtifact,
    ChaptersArtifact,
    InsightsArtifact,
    ReportArtifact,
    SpeechArtifact,
    SuggestionsArtifact,
    TranscriptArtifact,
    TurnsArtifact,
)


class JobContext(Protocol):
    """Контекст выполнения задачи конвейера."""

    job_id: str
    job_dir: Path


class PipelineStep(Protocol):
    """Протокол отдельного шага конвейера."""

    stage: str
    produces: str
    requires: tuple[str, ...]

    def run(self, ctx: JobContext, cfg: AppConfig) -> Path:
        """Запускает выполнение шага конвейера."""
        ...


@dataclass(frozen=True)
class StepDefinition:
    """Декларация шага конвейера с целевым артефактом и моделью валидации."""

    stage: str
    produces: str
    requires: tuple[str, ...]
    area: str
    model_cls: type[BaseModel]

    def run(self, ctx: Any, cfg: AppConfig) -> Path:
        """В версии D0 вызывает StageNotImplementedError без создания артефакта."""
        raise StageNotImplementedError(stage=self.stage)


# Девять стадий в строгом соответствии с контрактом
PIPELINE_STEPS: list[StepDefinition] = [
    StepDefinition(
        stage="normalize",
        produces="audio.json",
        requires=(),
        area="audio",
        model_cls=AudioArtifact,
    ),
    StepDefinition(
        stage="vad",
        produces="speech.json",
        requires=("audio.json",),
        area="vad",
        model_cls=SpeechArtifact,
    ),
    StepDefinition(
        stage="diarize",
        produces="turns.json",
        requires=("audio.json", "speech.json"),
        area="diarization",
        model_cls=TurnsArtifact,
    ),
    StepDefinition(
        stage="asr",
        produces="transcript.json",
        requires=("audio.json", "turns.json"),
        area="asr",
        model_cls=TranscriptArtifact,
    ),
    StepDefinition(
        stage="correction_suggest",
        produces="suggestions.json",
        requires=("transcript.json",),
        area="correction",
        model_cls=SuggestionsArtifact,
    ),
    StepDefinition(
        stage="chunk",
        produces="chapters.json",
        requires=("transcript.json",),
        area="chunking",
        model_cls=ChaptersArtifact,
    ),
    StepDefinition(
        stage="titles",
        produces="chapters.json",
        requires=("chapters.json", "transcript.json"),
        area="llm",
        model_cls=ChaptersArtifact,
    ),
    StepDefinition(
        stage="insights_extract",
        produces="insights.json",
        requires=("chapters.json", "transcript.json"),
        area="llm",
        model_cls=InsightsArtifact,
    ),
    StepDefinition(
        stage="report",
        produces="report.json",
        requires=("insights.json", "chapters.json"),
        area="llm",
        model_cls=ReportArtifact,
    ),
]

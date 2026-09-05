"""Модели артефактов пайплайна."""

from transcriber.models.artifacts import (
    AudioArtifact,
    ChaptersArtifact,
    InsightsArtifact,
    JobArtifact,
    QualityArtifact,
    ReportArtifact,
    SpeechArtifact,
    SuggestionsArtifact,
    TranscriptArtifact,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)

__all__ = [
    "AudioArtifact",
    "ChaptersArtifact",
    "InsightsArtifact",
    "JobArtifact",
    "QualityArtifact",
    "ReportArtifact",
    "SpeechArtifact",
    "SuggestionsArtifact",
    "TranscriptArtifact",
    "TurnsArtifact",
    "dump_artifact",
    "load_artifact",
]

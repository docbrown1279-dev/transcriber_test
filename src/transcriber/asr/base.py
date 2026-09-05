"""Интерфейс (порт) этапа автоматического распознавания речи (ASR)."""

from pathlib import Path
from typing import Protocol

from transcriber.config.schema import AsrConfig
from transcriber.models.artifacts import TranscriptArtifact, TurnsArtifact


class AsrEngine(Protocol):
    """Протокол движка распознавания речи."""

    name: str

    def transcribe(
        self,
        wav: Path,
        turns: TurnsArtifact,
        cfg: AsrConfig,
    ) -> TranscriptArtifact:
        """Выполняет распознавание речи по репликам дикторов и формирует стенограмму."""
        ...

"""Интерфейс (порт) этапа диаризации дикторов."""

from pathlib import Path
from typing import Protocol

from transcriber.config.schema import DiarizationConfig
from transcriber.models.artifacts import SpeechArtifact, TurnsArtifact


class Diarizer(Protocol):
    """Протокол сегментации речи по дикторам."""

    name: str

    def diarize(
        self,
        wav: Path,
        speech: SpeechArtifact,
        cfg: DiarizationConfig,
    ) -> TurnsArtifact:
        """Разбивает речевые интервалы на реплики конкретных дикторов с последующим слиянием."""
        ...

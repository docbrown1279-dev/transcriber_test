"""Интерфейс (порт) детектора голосовой активности (VAD)."""

from pathlib import Path
from typing import Protocol

from transcriber.config.schema import VadConfig
from transcriber.models.artifacts import SpeechArtifact


class VoiceActivityDetector(Protocol):
    """Протокол детектора речевой активности."""

    name: str

    def detect(self, wav: Path, cfg: VadConfig) -> SpeechArtifact:
        """Обнаруживает речевые интервалы во входном wav-файле."""
        ...

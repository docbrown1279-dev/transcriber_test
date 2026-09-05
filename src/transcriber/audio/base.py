"""Интерфейс (порт) этапа нормализации аудио."""

from pathlib import Path
from typing import Protocol

from transcriber.config.schema import AudioConfig
from transcriber.models.artifacts import AudioArtifact


class AudioNormalizer(Protocol):
    """Протокол компонента нормализации и проверки громкости аудио."""

    def normalize(self, source: Path, dest: Path, cfg: AudioConfig) -> AudioArtifact:
        """Нормализует исходный аудиофайл в формат 16 кГц моно WAV и применяет линейное усиление."""
        ...

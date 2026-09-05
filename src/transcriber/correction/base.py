"""Интерфейс (порт) этапа проверки и подсказки терминов."""

from typing import Protocol

from transcriber.config.schema import CorrectionConfig
from transcriber.models.artifacts import SuggestionsArtifact, TranscriptArtifact


class TermSuggester(Protocol):
    """Протокол поиска и предложения исправлений специализированных терминов."""

    name: str

    def suggest(
        self,
        transcript: TranscriptArtifact,
        cfg: CorrectionConfig,
    ) -> SuggestionsArtifact:
        """Анализирует текст стенограммы и формирует список предложений по терминам."""
        ...

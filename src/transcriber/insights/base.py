"""Интерфейс (порт) этапа извлечения инсайтов и ключевых тезисов."""

from typing import Protocol

from transcriber.config.schema import AppConfig
from transcriber.llm.base import LlmClient
from transcriber.models.artifacts import ChaptersArtifact, InsightsArtifact, TranscriptArtifact


class InsightExtractor(Protocol):
    """Протокол извлечения ключевых фактов, решений и открытых вопросов встречи."""

    name: str

    def extract(
        self,
        chapters: ChaptersArtifact,
        transcript: TranscriptArtifact,
        llm: LlmClient,
        cfg: AppConfig,
    ) -> InsightsArtifact:
        """Извлекает тезисы и инсайты по каждой главе с привязкой к исходным репликам."""
        ...

"""Интерфейсы (порты) эмбеддингов и семантической сегментации на главы."""

from collections.abc import Sequence
from typing import Any, Protocol

import numpy as np

from transcriber.config.schema import ChunkingConfig
from transcriber.models.artifacts import ChaptersArtifact, TranscriptArtifact


class EmbeddingBackend(Protocol):
    """Протокол генерации текстовых векторных представлений (эмбеддингов)."""

    name: str

    def encode(self, texts: Sequence[str]) -> np.ndarray[Any, Any]:
        """Генерирует векторные представления для последовательности фрагментов текста."""
        ...


class Chunker(Protocol):
    """Протокол группировки реплик в связные тематические главы."""

    name: str

    def chunk(
        self,
        transcript: TranscriptArtifact,
        embedder: EmbeddingBackend,
        cfg: ChunkingConfig,
    ) -> ChaptersArtifact:
        """Разбивает стенограмму на главы с учетом сходства дикторов и семантической близости."""
        ...

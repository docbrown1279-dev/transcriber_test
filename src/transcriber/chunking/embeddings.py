"""Sentence-transformers backend for semantic chapter merging."""

from collections.abc import Sequence
from typing import Any

import numpy as np


class RubertTiny2EmbeddingBackend:
    """Создает нормализованные эмбеддинги моделью rubert-tiny2."""

    name = "rubert_tiny2"

    def __init__(self, model_id: str = "cointegrated/rubert-tiny2") -> None:
        self._model_id = model_id
        self._model: Any | None = None

    def _load_model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "rubert_tiny2 requires the optional 'embed' dependencies"
                ) from exc
            self._model = SentenceTransformer(self._model_id, device="cpu")
        return self._model

    def encode(self, texts: Sequence[str]) -> np.ndarray[Any, Any]:
        """Кодирует тексты в нормализованные векторы с плавающей точкой."""
        if not texts:
            return np.empty((0, 0), dtype=np.float32)
        vectors = self._load_model().encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return np.asarray(vectors, dtype=np.float32)

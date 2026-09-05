"""Интерфейс (порт) клиента больших языковых моделей (LLM)."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field


class LlmResponse(BaseModel):
    """Структура унифицированного ответа языковой модели."""

    model_config = ConfigDict(extra="forbid")

    text: str
    provider: str
    model: str
    prompt_id: str
    tokens_in: int = Field(ge=0)
    tokens_out: int = Field(ge=0)
    runtime_sec: float = Field(ge=0.0)


class LlmClient(Protocol):
    """Протокол взаимодействия с провайдерами языковых моделей."""

    name: str

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> LlmResponse:
        """Выполняет запрос генерации текста по промпту."""
        ...

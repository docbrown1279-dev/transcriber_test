"""Construction and call-parameter resolution for LLM clients."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from transcriber.config.schema import LlmConfig, LlmTaskConfig
from transcriber.llm.base import LlmClient, LlmResponse
from transcriber.llm.gemini import GeminiLlmClient
from transcriber.llm.openai_compat import OpenAiCompatLlmClient


@dataclass(frozen=True)
class LlmCallOptions:
    """Итоговые параметры одного вызова языковой модели."""

    max_tokens: int | None
    temperature: float | None
    response_format: str | None
    timeout_sec: float | None
    extra: dict[str, object] | None


def resolve_call_options(cfg: LlmConfig, task: LlmTaskConfig) -> LlmCallOptions:
    """Объединяет общие параметры генерации с переопределениями задачи."""
    return LlmCallOptions(
        max_tokens=task.max_tokens
        if task.max_tokens is not None
        else cfg.base_llm.max_tokens,
        temperature=task.temperature
        if task.temperature is not None
        else cfg.base_llm.temperature,
        response_format=task.response_format
        if task.response_format is not None
        else cfg.base_llm.response_format,
        timeout_sec=cfg.base_llm.timeout_sec,
        extra=None,
    )


def make_client(cfg: LlmConfig) -> LlmClient:
    """Создаёт транспорт для выбранного LLM-бэкенда."""
    backend = cfg.active_backend
    timeout = cfg.base_llm.timeout_sec
    if backend.client == "gemini":
        return GeminiLlmClient(
            model=backend.model,
            api_key_env=backend.api_key_env,
            timeout_sec=timeout,
        )
    if backend.client == "openai_compat":
        if backend.base_url is None:
            raise ValueError(f"Backend {cfg.backend} requires base_url")
        return OpenAiCompatLlmClient(
            provider=cfg.backend,
            model=backend.model,
            api_key_env=backend.api_key_env,
            base_url=backend.base_url,
            timeout_sec=timeout,
        )
    raise ValueError(f"Unsupported LLM client: {backend.client}")


def complete_json(
    client: LlmClient,
    *,
    prompt: str,
    prompt_id: str,
    schema: dict[str, Any],
    cfg: LlmConfig,
    task: LlmTaskConfig,
) -> LlmResponse:
    """Выполняет один JSON-вызов с объединёнными параметрами."""
    options = resolve_call_options(cfg, task)
    return client.complete(
        prompt,
        prompt_id=prompt_id,
        max_tokens=options.max_tokens,
        temperature=options.temperature,
        json_schema=schema,
        extra=options.extra,
    )

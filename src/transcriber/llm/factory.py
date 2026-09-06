"""Construction and call-parameter resolution for LLM clients."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from transcriber.config.loader import find_config_dir
from transcriber.config.schema import LlmConfig, LlmTaskConfig
from transcriber.llm.base import LlmClient, LlmResponse
from transcriber.llm.gemini import GeminiLlmClient
from transcriber.llm.openai_compat import OpenAiCompatLlmClient

__all__ = [
    "LlmCallOptions",
    "OpenAiCompatLlmClient",
    "complete_json",
    "load_backend_extra",
    "make_client",
    "resolve_call_options",
]

_OPTION_KEYS = frozenset({"temperature", "max_tokens", "response_format", "timeout_sec"})


@dataclass(frozen=True)
class LlmCallOptions:
    """Итоговые параметры одного вызова языковой модели."""

    max_tokens: int | None
    temperature: float | None
    response_format: str | None
    timeout_sec: float | None
    extra: dict[str, object] | None


def load_backend_extra(cfg: LlmConfig, config_dir: Path | str | None = None) -> dict[str, Any]:
    """Читает yaml из backends.*.extra_config относительно каталога config/."""
    path = cfg.active_backend.extra_config
    if not path:
        return {}
    root = find_config_dir(config_dir=config_dir)
    extra_path = (root / path).resolve()
    if not str(extra_path).startswith(str(root.resolve())):
        raise ValueError(f"extra_config path escapes config dir: {path}")
    if not extra_path.is_file():
        raise FileNotFoundError(f"LLM extra_config not found: {extra_path}")
    raw = yaml.safe_load(extra_path.read_text(encoding="utf-8"))
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError(f"LLM extra_config must be a mapping: {extra_path}")
    return raw


def resolve_call_options(
    cfg: LlmConfig,
    task: LlmTaskConfig,
    *,
    config_dir: Path | str | None = None,
) -> LlmCallOptions:
    """Объединяет base_llm ← backend.extra_config ← переопределения задачи."""
    temperature = cfg.base_llm.temperature
    max_tokens = cfg.base_llm.max_tokens
    response_format = cfg.base_llm.response_format
    timeout_sec = cfg.base_llm.timeout_sec
    extra: dict[str, object] = {}

    backend_extra = load_backend_extra(cfg, config_dir=config_dir)
    for key, value in backend_extra.items():
        if key in _OPTION_KEYS:
            if key == "temperature":
                temperature = value
            elif key == "max_tokens":
                max_tokens = value
            elif key == "response_format":
                response_format = value
            elif key == "timeout_sec":
                timeout_sec = value
        else:
            extra[key] = value

    if task.max_tokens is not None:
        max_tokens = task.max_tokens
    if task.temperature is not None:
        temperature = task.temperature
    if task.response_format is not None:
        response_format = task.response_format

    return LlmCallOptions(
        max_tokens=max_tokens,
        temperature=temperature,
        response_format=response_format,
        timeout_sec=timeout_sec,
        extra=extra or None,
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

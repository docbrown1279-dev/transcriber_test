"""OpenAI-compatible text transport for NVIDIA and Qwen APIs."""

from __future__ import annotations

import os
from time import monotonic
from typing import Any

import httpx

from transcriber.llm.base import LlmResponse


class OpenAiCompatLlmClient:
    """Выполняет JSON-запросы к OpenAI-совместимому API."""

    name = "openai_compat"

    def __init__(
        self,
        *,
        provider: str,
        model: str,
        api_key_env: str,
        base_url: str,
        timeout_sec: float | None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._api_key_env = api_key_env
        self._base_url = base_url.rstrip("/")
        self._timeout_sec = timeout_sec

    def complete(
        self,
        prompt: str,
        *,
        prompt_id: str,
        max_tokens: int | None,
        temperature: float | None,
        json_schema: dict[str, Any] | None,
        extra: dict[str, object] | None = None,
    ) -> LlmResponse:
        """Отправляет только текст и возвращает унифицированный ответ провайдера."""
        api_key = os.environ.get(self._api_key_env)
        if not api_key:
            raise RuntimeError(f"Missing required API key variable: {self._api_key_env}")

        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [{"role": "user", "content": prompt}],
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        if temperature is not None:
            payload["temperature"] = temperature
        if json_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": prompt_id.replace("/", "_"), "schema": json_schema},
            }
        if extra:
            payload.update(extra)

        started = monotonic()
        try:
            response = httpx.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
                timeout=self._timeout_sec,
            )
            response.raise_for_status()
            body = response.json()
            text = body["choices"][0]["message"]["content"]
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise RuntimeError(
                f"OpenAI-compatible request failed for {self._provider} prompt {prompt_id}"
            ) from exc
        if not isinstance(text, str) or not text:
            raise RuntimeError(
                f"OpenAI-compatible API returned an empty response for {self._provider}"
            )

        usage = body.get("usage", {})
        return LlmResponse(
            text=text,
            provider=self._provider,
            model=self._model,
            prompt_id=prompt_id,
            tokens_in=int(usage.get("prompt_tokens", 0) or 0),
            tokens_out=int(usage.get("completion_tokens", 0) or 0),
            runtime_sec=round(monotonic() - started, 3),
        )

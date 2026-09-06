"""Gemini text-only client."""

from __future__ import annotations

import os
from time import monotonic
from typing import Any

from transcriber.llm.base import LlmResponse


class GeminiLlmClient:
    """Выполняет текстовые запросы к Gemini 2.5 Flash."""

    name = "gemini"

    def __init__(
        self,
        *,
        model: str,
        api_key_env: str,
        timeout_sec: float | None,
    ) -> None:
        self._model = model
        self._api_key_env = api_key_env
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
        try:
            from google import genai
            from google.genai import types
        except ImportError as exc:
            raise RuntimeError("Gemini requires the optional 'llm' dependencies") from exc

        started = monotonic()
        try:
            client_args: dict[str, Any] = {"api_key": api_key}
            if self._timeout_sec is not None:
                client_args["http_options"] = types.HttpOptions(
                    timeout=int(self._timeout_sec * 1000)
                )
            client = genai.Client(**client_args)
            generation_args: dict[str, Any] = {
                "response_mime_type": "application/json",
            }
            if max_tokens is not None:
                generation_args["max_output_tokens"] = max_tokens
            if temperature is not None:
                generation_args["temperature"] = temperature
            if json_schema is not None:
                generation_args["response_json_schema"] = json_schema
            if extra:
                generation_args.update(extra)
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(**generation_args),
            )
        except Exception as exc:
            raise RuntimeError(
                f"Gemini request failed for prompt {prompt_id} using model {self._model}"
            ) from exc

        text = response.text
        if not text:
            raise RuntimeError(f"Gemini returned an empty response for model {self._model}")
        usage: Any = getattr(response, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)
        return LlmResponse(
            text=text,
            provider=self.name,
            model=self._model,
            prompt_id=prompt_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            runtime_sec=round(monotonic() - started, 3),
        )

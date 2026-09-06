"""Gemini text-only client for chapter title generation."""

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
        model: str = "gemini-2.5-flash",
        api_key_env: str = "GEMINI_API_KEY",
        prompt_id: str = "title_p1_v1",
    ) -> None:
        self._model = model
        self._api_key_env = api_key_env
        self._prompt_id = prompt_id

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
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
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                    response_mime_type="application/json",
                    response_json_schema={
                        "type": "object",
                        "properties": {"title": {"type": "string"}},
                        "required": ["title"],
                        "additionalProperties": False,
                    },
                ),
            )
        except Exception as exc:
            raise RuntimeError(f"Gemini title request failed for model {self._model}") from exc

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
            prompt_id=self._prompt_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            runtime_sec=round(monotonic() - started, 3),
        )

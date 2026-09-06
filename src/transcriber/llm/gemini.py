"""Gemini text-only client."""

from __future__ import annotations

import logging
import os
from time import monotonic
from typing import Any

from transcriber.llm.base import LlmResponse
from transcriber.llm.errors import exception_summary

logger = logging.getLogger(__name__)


def _response_text(response: Any) -> str:
    """Достаёт текст ответа, пропуская thought-части Gemini 2.5."""
    direct = getattr(response, "text", None)
    if direct:
        return str(direct)
    chunks: list[str] = []
    for candidate in getattr(response, "candidates", None) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", None) or []:
            if getattr(part, "thought", False):
                continue
            piece = getattr(part, "text", None)
            if piece:
                chunks.append(str(piece))
    return "".join(chunks)


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
        logger.info("llm request prompt_id=%s model=%s", prompt_id, self._model)
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
            generation_args["automatic_function_calling"] = types.AutomaticFunctionCallingConfig(
                disable=True
            )
            generation_args.setdefault(
                "thinking_config", types.ThinkingConfig(thinking_budget=0)
            )
            response = client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=types.GenerateContentConfig(**generation_args),
            )
        except Exception as exc:
            summary = exception_summary(exc)
            logger.error(
                "llm error provider=gemini prompt_id=%s model=%s err=%s",
                prompt_id,
                self._model,
                summary,
            )
            raise RuntimeError(
                f"Gemini request failed for prompt {prompt_id} using model {self._model}: {summary}"
            ) from exc

        text = _response_text(response)
        if not text:
            raise RuntimeError(f"Gemini returned an empty response for model {self._model}")
        usage: Any = getattr(response, "usage_metadata", None)
        tokens_in = int(getattr(usage, "prompt_token_count", 0) or 0)
        tokens_out = int(getattr(usage, "candidates_token_count", 0) or 0)
        logger.info(
            "llm response prompt_id=%s tokens_in=%s tokens_out=%s",
            prompt_id,
            tokens_in,
            tokens_out,
        )
        return LlmResponse(
            text=text,
            provider=self.name,
            model=self._model,
            prompt_id=prompt_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            runtime_sec=round(monotonic() - started, 3),
        )

"""OpenAI-compatible text transport for NVIDIA and Qwen APIs."""

from __future__ import annotations

import logging
import os
from time import monotonic
from typing import Any

import httpx

from transcriber.llm.base import LlmResponse
from transcriber.llm.errors import exception_summary, httpx_error_summary

logger = logging.getLogger(__name__)


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
                "json_schema": {
                    "name": prompt_id.replace("/", "_"),
                    "schema": json_schema,
                },
            }
        if extra:
            payload.update(extra)

        started = monotonic()
        logger.info(
            "llm request provider=%s prompt_id=%s model=%s",
            self._provider,
            prompt_id,
            self._model,
        )
        try:
            body = self._chat_completions(payload, api_key, json_schema is not None)
            text = body["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as exc:
            summary = httpx_error_summary(exc.response)
            logger.error(
                "llm http error provider=%s prompt_id=%s %s",
                self._provider,
                prompt_id,
                summary,
            )
            raise RuntimeError(
                f"{self._provider} HTTP {exc.response.status_code} for {prompt_id}: {summary}"
            ) from exc
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            logger.error(
                "llm request failed provider=%s prompt_id=%s err=%s",
                self._provider,
                prompt_id,
                exception_summary(exc),
            )
            raise RuntimeError(
                f"{self._provider} request failed for {prompt_id}: {exception_summary(exc)}"
            ) from exc
        if not isinstance(text, str) or not text:
            logger.error(
                "llm empty response provider=%s prompt_id=%s",
                self._provider,
                prompt_id,
            )
            raise RuntimeError(
                f"OpenAI-compatible API returned an empty response for {self._provider}"
            )

        usage = body.get("usage", {})
        tokens_in = int(usage.get("prompt_tokens", 0) or 0)
        tokens_out = int(usage.get("completion_tokens", 0) or 0)
        logger.info(
            "llm response provider=%s prompt_id=%s tokens_in=%s tokens_out=%s",
            self._provider,
            prompt_id,
            tokens_in,
            tokens_out,
        )
        return LlmResponse(
            text=text,
            provider=self._provider,
            model=self._model,
            prompt_id=prompt_id,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            runtime_sec=round(monotonic() - started, 3),
        )

    def _chat_completions(
        self,
        payload: dict[str, Any],
        api_key: str,
        allow_json_object_fallback: bool,
    ) -> dict[str, Any]:
        response = self._post(payload, api_key)
        if (
            response.status_code == 400
            and allow_json_object_fallback
            and isinstance(payload.get("response_format"), dict)
            and payload["response_format"].get("type") == "json_schema"
        ):
            logger.warning(
                "llm json_schema rejected provider=%s %s; retrying json_object",
                self._provider,
                httpx_error_summary(response),
            )
            retry_payload = dict(payload)
            retry_payload["response_format"] = {"type": "json_object"}
            response = self._post(retry_payload, api_key)
        response.raise_for_status()
        body: Any = response.json()
        if not isinstance(body, dict):
            raise ValueError("chat completions response is not an object")
        return body

    def _post(self, payload: dict[str, Any], api_key: str) -> httpx.Response:
        return httpx.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=self._timeout_sec,
        )

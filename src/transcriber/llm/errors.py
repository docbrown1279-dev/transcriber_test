"""Санитизированные сообщения об ошибках LLM API (без секретов и текста промпта)."""

from __future__ import annotations

from typing import Any

import httpx

_MAX_DETAIL = 240


def short_text(value: object, limit: int = _MAX_DETAIL) -> str:
    """Обрезает произвольный текст ошибки до безопасной длины."""
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def httpx_error_summary(response: httpx.Response) -> str:
    """Краткое описание HTTP-ответа API: status + code/message, без тела промпта."""
    detail = _json_error_fields(response)
    if detail:
        return f"status={response.status_code} {detail}"
    return f"status={response.status_code} body_chars={len(response.text)}"


def exception_summary(exc: BaseException) -> str:
    """Однострочное описание исключения без значений секретов."""
    status = getattr(exc, "status_code", None)
    parts = [type(exc).__name__]
    if status is not None:
        parts.append(f"status={status}")
    message = short_text(exc)
    if message:
        parts.append(message)
    return short_text(" ".join(parts))


def _json_error_fields(response: httpx.Response) -> str | None:
    try:
        data: Any = response.json()
    except ValueError:
        return None
    err = data.get("error", data) if isinstance(data, dict) else None
    if not isinstance(err, dict):
        return None
    bits: list[str] = []
    for key in ("code", "type", "status", "message", "msg"):
        value = err.get(key)
        if value is not None and value != "":
            bits.append(f"{key}={value}")
    return short_text(" ".join(bits)) if bits else None

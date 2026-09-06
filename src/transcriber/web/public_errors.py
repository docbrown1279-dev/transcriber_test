"""Сообщения для пользователя: лимиты — явно, остальное — общая формулировка.

Технические детали (ffmpeg, traceback, id стадий) остаются только в логах.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

USER_GENERIC = "Ошибка, попробуйте позже."
USER_SERVER = "Ошибка сервера."

_EXPOSED_STATUSES = {400, 403, 404, 409, 413, 429}
_TECHNICAL_MARKERS = (
    "ffprobe",
    "ffmpeg",
    "traceback",
    "runtimeerror",
    "calledprocesserror",
    "exception",
    "failed_precondition",
    ".py",
    "stdout",
    "stderr",
)


def looks_technical(message: str | None) -> bool:
    """True, если текст похож на внутреннюю ошибку, а не на лимит."""
    if not message:
        return True
    lower = message.lower()
    return any(marker in lower for marker in _TECHNICAL_MARKERS)


def client_message(status_code: int, message: str | None, *, expose: bool | None = None) -> str:
    """Текст для HTML/JSON. Лимиты и явные пользовательские 4xx — как есть."""
    if expose is None:
        expose = status_code in _EXPOSED_STATUSES and not looks_technical(message)
    if expose and message:
        return message
    if status_code >= 500:
        return USER_SERVER
    return USER_GENERIC


def public_job_error(state: str, error: str | None) -> str | None:
    """Для страницы прогресса: только failed, без текста исключения."""
    if state != "failed":
        return None
    if error and not looks_technical(error) and error.strip():
        return error
    return USER_GENERIC


def overall_progress_pct(stages: list[Any], total_stages: int, state: str) -> int:
    """Грубая доля готовых стадий (ingest + пайплайн), 0–100."""
    if state == "done":
        return 100
    denom = max(total_stages, 1)
    finished = sum(1 for item in stages if getattr(item, "status", "") == "done")
    running = next((item for item in stages if getattr(item, "status", "") == "running"), None)
    frac = finished / denom
    if running is not None:
        frac += (float(getattr(running, "pct", 0) or 0) / 100.0) / denom
    return max(0, min(100, int(frac * 100)))


def elapsed_seconds(created_at: str, *, now: datetime | None = None) -> int:
    """Секунды с created_at (ISO) до now."""
    parsed = _parse_iso(created_at)
    if parsed is None:
        return 0
    moment = now or datetime.now(timezone.utc)
    return max(0, int((moment - parsed).total_seconds()))


def processing_seconds(job: Any) -> int:
    """Длительность обработки: created_at → finished_at, иначе сумма runtime стадий.

    Для running — wall-clock с создания. Не растёт после done при перезагрузке страницы.
    """
    state = getattr(job, "state", "")
    created = getattr(job, "created_at", "") or ""
    finished = getattr(job, "finished_at", None)
    if state in {"done", "failed"}:
        if finished:
            end = _parse_iso(str(finished))
            start = _parse_iso(created)
            if end is not None and start is not None:
                return max(0, int((end - start).total_seconds()))
        total = 0.0
        for item in getattr(job, "stages", []) or []:
            value = getattr(item, "runtime_sec", None)
            if value is not None:
                total += float(value)
        if total > 0:
            return int(total)
    return elapsed_seconds(created)


def _parse_iso(value: str) -> datetime | None:
    text = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def format_elapsed_ru(seconds: float) -> str:
    """Человекочитаемое время: «3 мин 12 с»."""
    total = max(0, int(seconds))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours} ч {minutes} мин {secs} с"
    if minutes:
        return f"{minutes} мин {secs} с"
    return f"{secs} с"

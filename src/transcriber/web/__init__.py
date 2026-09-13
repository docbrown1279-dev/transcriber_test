"""Модуль веб-интерфейса и API."""

from typing import Any

from transcriber.web.health import ComponentHealth, probe_audio_file, run_self_check
from transcriber.web.limits import (
    DurationDecision,
    SizeCheck,
    duration_trim_decision,
    is_loopback_client,
)
from transcriber.web.url_stub import classify_media_url

__all__ = [
    "ComponentHealth",
    "DurationDecision",
    "SizeCheck",
    "app",
    "classify_media_url",
    "duration_trim_decision",
    "is_loopback_client",
    "probe_audio_file",
    "run_self_check",
]


def __getattr__(name: str) -> Any:
    """Lazy ``app`` export — avoids circular import with ``jobs.queue``."""
    if name == "app":
        from transcriber.web.app import app as _app

        return _app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

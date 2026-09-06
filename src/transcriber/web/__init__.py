"""Модуль веб-интерфейса и API."""

from transcriber.web.app import app
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

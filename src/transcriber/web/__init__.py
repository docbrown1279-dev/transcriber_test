"""Модуль веб-интерфейса и API."""

from transcriber.web.app import app
from transcriber.web.health import ComponentHealth, probe_audio_file, run_self_check

__all__ = ["ComponentHealth", "app", "probe_audio_file", "run_self_check"]

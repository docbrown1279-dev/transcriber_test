"""Модуль конфигурации приложения."""

from transcriber.config.loader import load_config
from transcriber.config.schema import AppConfig

__all__ = ["AppConfig", "load_config"]

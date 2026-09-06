"""Модуль конфигурации приложения."""

from transcriber.config.loader import load_config, load_dotenv_into_environ
from transcriber.config.schema import AppConfig

__all__ = ["AppConfig", "load_config", "load_dotenv_into_environ"]

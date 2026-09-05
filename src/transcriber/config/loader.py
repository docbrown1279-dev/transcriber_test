"""Загрузчик конфигурационных профилей приложения.

Читает YAML-файлы конфигурации и валидирует их по строгой схеме AppConfig.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from transcriber.config.schema import AppConfig
from transcriber.errors import ConfigError


def _find_config_file(profile: str, config_dir: Path | str | None = None) -> Path:
    """Определяет путь к файлу конфигурации указанного профиля."""
    if config_dir is not None:
        path = Path(config_dir) / f"{profile}.yaml"
        if path.is_file():
            return path
        raise ConfigError(f"Config file not found at '{path}'")

    candidates = [
        Path(f"config/{profile}.yaml"),
        Path(__file__).resolve().parent.parent.parent.parent / "config" / f"{profile}.yaml",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise ConfigError(f"Config file for profile '{profile}' not found in candidates: {candidates}")


def load_config(profile: str | None = None, config_dir: Path | str | None = None) -> AppConfig:
    """Загружает и валидирует конфигурацию приложения для указанного профиля.

    Если профиль не передан явно, значение считывается из переменной окружения
    APP_PROFILE (по умолчанию 'demo').
    """
    resolved_profile = profile or os.environ.get("APP_PROFILE", "demo")
    config_path = _find_config_file(resolved_profile, config_dir=config_dir)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data: Any = yaml.safe_load(f)
    except Exception as exc:
        raise ConfigError(f"Failed to read YAML file '{config_path}': {exc}") from exc

    if not isinstance(raw_data, dict):
        raise ConfigError(f"Configuration file '{config_path}' must contain a YAML mapping")

    try:
        return AppConfig.model_validate(raw_data)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        key_path = ".".join(str(part) for part in first_error["loc"])
        msg = first_error["msg"]
        raise ConfigError(f"Validation failed for '{key_path}': {msg}", key_path=key_path) from exc

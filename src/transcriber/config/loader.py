"""Загрузчик конфигурационных профилей приложения.

Читает base.yaml, deep-merge с profiles/{profile}.yaml, валидирует AppConfig.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from transcriber.config.schema import AppConfig
from transcriber.errors import ConfigError


def _repo_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "config"


def _find_config_dir(config_dir: Path | str | None = None) -> Path:
    if config_dir is not None:
        path = Path(config_dir)
        if path.is_dir():
            return path
        raise ConfigError(f"Config directory not found at '{path}'")

    candidates = [Path("config"), _repo_config_dir()]
    for candidate in candidates:
        if candidate.is_dir() and (candidate / "base.yaml").is_file():
            return candidate

    raise ConfigError(f"Config directory with base.yaml not found in candidates: {candidates}")


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge overlay into a copy of base. Overlay scalars/lists win."""
    result: dict[str, Any] = dict(base)
    for key, value in overlay.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw_data: Any = yaml.safe_load(f)
    except Exception as exc:
        raise ConfigError(f"Failed to read YAML file '{path}': {exc}") from exc

    if raw_data is None:
        return {}
    if not isinstance(raw_data, dict):
        raise ConfigError(f"Configuration file '{path}' must contain a YAML mapping")
    return raw_data


def load_config(profile: str | None = None, config_dir: Path | str | None = None) -> AppConfig:
    """Загружает base + profile overlay и валидирует конфигурацию.

    Если профиль не передан явно, значение считывается из переменной окружения
    APP_PROFILE (по умолчанию 'demo').
    """
    resolved_profile = profile or os.environ.get("APP_PROFILE", "demo")
    root = _find_config_dir(config_dir=config_dir)

    base_path = root / "base.yaml"
    if not base_path.is_file():
        raise ConfigError(f"Base config not found at '{base_path}'")

    overlay_path = root / "profiles" / f"{resolved_profile}.yaml"
    if not overlay_path.is_file():
        # Backward-compatible single-file profile (tests may still use this).
        legacy = root / f"{resolved_profile}.yaml"
        if legacy.is_file():
            merged = _load_yaml(legacy)
        else:
            raise ConfigError(
                f"Profile overlay not found at '{overlay_path}' "
                f"(and no legacy '{legacy}')"
            )
    else:
        merged = deep_merge(_load_yaml(base_path), _load_yaml(overlay_path))

    # Ensure profile field matches selection
    app_section = merged.setdefault("app", {})
    if isinstance(app_section, dict):
        app_section["profile"] = resolved_profile

    try:
        return AppConfig.model_validate(merged)
    except ValidationError as exc:
        first_error = exc.errors()[0]
        key_path = ".".join(str(part) for part in first_error["loc"])
        msg = first_error["msg"]
        raise ConfigError(f"Validation failed for '{key_path}': {msg}", key_path=key_path) from exc

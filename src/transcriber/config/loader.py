"""Загрузчик конфигурационных профилей приложения.

Читает base.yaml, base_llm.yaml и profiles/{profile}.yaml, затем валидирует AppConfig.
Опционально подгружает `.env` в окружение процесса (без логирования значений).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from transcriber.config.schema import AppConfig
from transcriber.errors import ConfigError

logger = logging.getLogger(__name__)

_DOTENV_LOADED_PATHS: set[Path] = set()

# Secrets and salts only — never log values. Profile is not a secret.
_ENV_NAME_CHECKS: tuple[str, ...] = (
    "JOB_IP_SALT",
    "GEMINI_API_KEY",
    "NVIDIA_API_KEY",
    "QWEN_API_KEY",
    "HF_TOKEN",
)
# These keys in `.env` are ignored; switch profile in config/base.yaml or CLI `--profile`.
_DOTENV_SKIP_KEYS: frozenset[str] = frozenset({"APP_PROFILE"})


def _repo_config_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent / "config"


def find_config_dir(config_dir: Path | str | None = None) -> Path:
    """Возвращает каталог config/ с base.yaml."""
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


# Backward-compatible private alias used by older call sites.
_find_config_dir = find_config_dir


def load_dotenv_into_environ(config_root: Path | str | None = None) -> list[Path]:
    """Подставляет переменные из `.env`, не перезаписывая уже заданные в окружении.

    Ищет `.env` в cwd и в корне репозитория (рядом с `config/`). Значения секретов
    не логируются — только пути файлов и *имена* переменных (set/missing).
    """
    root = Path(config_root) if config_root is not None else _repo_config_dir()
    candidates: list[Path] = []
    for raw in (Path.cwd() / ".env", root.parent / ".env"):
        resolved = raw.resolve()
        if resolved not in candidates:
            candidates.append(resolved)

    existing = [path for path in candidates if path.is_file()]
    if not existing:
        logger.info("no .env file found (checked %s)", [str(p) for p in candidates])
        _log_env_name_presence()
        return []

    try:
        from dotenv import dotenv_values
    except ImportError:
        logger.error(
            "python-dotenv is not installed; cannot load %s",
            [str(p) for p in existing],
        )
        _log_env_name_presence()
        return []

    for env_path in existing:
        _apply_dotenv_file(env_path, read_values=dotenv_values)
        if env_path not in _DOTENV_LOADED_PATHS:
            logger.info("dotenv loaded from %s", env_path)
            _DOTENV_LOADED_PATHS.add(env_path)
    _log_env_name_presence()
    return existing


_DOTENV_SKIP_LOGGED = False


def _apply_dotenv_file(env_path: Path, read_values: Any) -> None:
    """Пишет в environ только секреты: ключи профиля из `.env` пропускаются."""
    global _DOTENV_SKIP_LOGGED
    values = read_values(env_path)
    skipped = sorted(key for key in values if key in _DOTENV_SKIP_KEYS)
    if skipped and not _DOTENV_SKIP_LOGGED:
        logger.warning(
            "ignoring keys in .env (not secrets): %s; set app.profile in config/base.yaml "
            "or pass --profile / process env APP_PROFILE",
            skipped,
        )
        _DOTENV_SKIP_LOGGED = True
    for key, value in values.items():
        if key in _DOTENV_SKIP_KEYS or value is None:
            continue
        if key not in os.environ:
            os.environ[key] = value


_ENV_PRESENCE_LOGGED = False


def _log_env_name_presence() -> None:
    """Пишет, какие известные имена переменных заданы; без значений."""
    global _ENV_PRESENCE_LOGGED
    present = [name for name in _ENV_NAME_CHECKS if os.environ.get(name)]
    missing = [name for name in _ENV_NAME_CHECKS if not os.environ.get(name)]
    if _ENV_PRESENCE_LOGGED:
        return
    _ENV_PRESENCE_LOGGED = True
    logger.info("env names set=%s missing=%s", present, missing)


# Backward-compatible private alias.
_load_dotenv_into_environ = load_dotenv_into_environ


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


def _profile_from_yaml(base_config: dict[str, Any]) -> str:
    app = base_config.get("app")
    if isinstance(app, dict):
        value = app.get("profile")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "demo"


def _resolve_profile(explicit: str | None, yaml_profile: str) -> str:
    """CLI `--profile` > process env APP_PROFILE > config/base.yaml app.profile > demo."""
    if explicit:
        return explicit
    env = os.environ.get("APP_PROFILE", "").strip()
    if env:
        return env
    return yaml_profile or "demo"


def load_config(profile: str | None = None, config_dir: Path | str | None = None) -> AppConfig:
    """Загружает base + overlay выбранного профиля и валидирует конфигурацию.

    Профиль берётся из аргумента, иначе из process env `APP_PROFILE` (не из `.env`),
    иначе из `config/base.yaml` → `app.profile` (по умолчанию demo).
    """
    root = _find_config_dir(config_dir=config_dir)
    load_dotenv_into_environ(root)

    base_path = root / "base.yaml"
    if not base_path.is_file():
        raise ConfigError(f"Base config not found at '{base_path}'")

    llm_path = root / "base_llm.yaml"
    if not llm_path.is_file():
        raise ConfigError(f"LLM base config not found at '{llm_path}'")

    base_config = deep_merge(_load_yaml(base_path), _load_yaml(llm_path))
    resolved_profile = _resolve_profile(profile, _profile_from_yaml(base_config))
    overlay_path = root / "profiles" / f"{resolved_profile}.yaml"
    if not overlay_path.is_file():
        # Backward-compatible single-file profile (tests may still use this).
        legacy = root / f"{resolved_profile}.yaml"
        if legacy.is_file():
            merged = deep_merge(base_config, _load_yaml(legacy))
        else:
            raise ConfigError(
                f"Profile overlay not found at '{overlay_path}' "
                f"(and no legacy '{legacy}')"
            )
    else:
        merged = deep_merge(base_config, _load_yaml(overlay_path))

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

"""Loading and rendering of immutable, package-owned LLM resources."""

import json
from pathlib import Path
import re
from typing import Any


_PLACEHOLDER = re.compile(r"\{\{[A-Za-z_][A-Za-z0-9_]*\}\}")
_PACKAGE_ROOT = Path(__file__).resolve().parent


def _resource_path(relative_path: str, expected_dir: str, suffix: str) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts or not relative_path.endswith(suffix):
        raise ValueError(f"Invalid LLM resource path: {relative_path!r}")
    resolved = (_PACKAGE_ROOT / path).resolve()
    allowed = (_PACKAGE_ROOT / expected_dir).resolve()
    if allowed not in resolved.parents:
        raise ValueError(f"LLM resource must be under {expected_dir}/: {relative_path!r}")
    if not resolved.is_file():
        raise FileNotFoundError(f"LLM resource not found: {relative_path}")
    return resolved


def load_prompt(prompt_path: str) -> str:
    """Загружает зафиксированный markdown-промпт по пути из конфигурации."""
    return _resource_path(prompt_path, "prompts", ".md").read_text(encoding="utf-8")


def load_schema(schema_path: str) -> dict[str, Any]:
    """Загружает JSON-схему ответа по пути из конфигурации."""
    value = json.loads(
        _resource_path(schema_path, "schemas", ".json").read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise ValueError(f"JSON schema must be an object: {schema_path}")
    return value


def render_prompt(template: str, values: dict[str, str]) -> str:
    """Подставляет значения в шаблон и отклоняет незаполненные плейсхолдеры."""
    rendered = template
    for name, value in values.items():
        rendered = rendered.replace("{{" + name + "}}", value)
    leftovers = sorted(set(_PLACEHOLDER.findall(rendered)))
    if leftovers:
        raise ValueError(f"Unresolved prompt placeholders: {', '.join(leftovers)}")
    return rendered

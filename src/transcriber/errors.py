"""Базовые и специализированные исключения приложения.

Каждое исключение явно указывает ошибочный компонент или параметр.
"""

from typing import Sequence


class TranscriberError(Exception):
    """Базовый класс для всех исключений транскрибатора."""


class ComponentUnavailableError(TranscriberError):
    """Компонент недоступен в выбранном профиле конфигурации."""

    def __init__(self, component: str, profile: str, hint: str) -> None:
        self.component = component
        self.profile = profile
        self.hint = hint
        super().__init__(
            f"Component '{component}' is unavailable in profile '{profile}'. Hint: {hint}"
        )


class UnknownComponentError(TranscriberError):
    """Неизвестный ключ компонента в реестре для указанной области."""

    def __init__(self, area: str, key: str) -> None:
        self.area = area
        self.key = key
        super().__init__(f"Unknown component key '{key}' for area '{area}'")


class StageNotImplementedError(TranscriberError):
    """Стадия конвейера еще не реализована в текущей версии."""

    def __init__(self, stage: str) -> None:
        self.stage = stage
        super().__init__(f"Stage '{stage}' is not implemented in this profile/version")


class ConfigError(TranscriberError):
    """Ошибка валидации или загрузки конфигурации."""

    def __init__(self, message: str, key_path: str | None = None) -> None:
        self.key_path = key_path
        if key_path:
            full_message = f"Config error at '{key_path}': {message}"
        else:
            full_message = f"Config error: {message}"
        super().__init__(full_message)


class PreflightError(TranscriberError):
    """Ошибка предварительной проверки окружения и входных данных."""

    def __init__(self, message: str, missing_items: Sequence[str] | None = None) -> None:
        self.missing_items = list(missing_items) if missing_items else []
        super().__init__(message)

"""Модуль проверок качества распознавания и соблюдения шлюзов."""

from transcriber.quality.checks import (
    CheckReport,
    CheckResult,
    check_latin_contamination,
    check_russian_ratio,
)
from transcriber.quality.ru_ratio import (
    RatioResult,
    count_latin_characters,
    russian_word_ratio,
)

__all__ = [
    "CheckReport",
    "CheckResult",
    "RatioResult",
    "check_latin_contamination",
    "check_russian_ratio",
    "count_latin_characters",
    "russian_word_ratio",
]

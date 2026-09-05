"""Оценка доли русских слов и детекция латинских символов.

Реализует проверку качества G1 согласно контракту quality_gates.md:
токены \\w+ длиной >= 2, нижний регистр, ё -> е, чисто кириллические токены
считаются русскими. Числа и пунктуация исключаются из подсчета.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

CYRILLIC_PATTERN = re.compile(r"^[\u0400-\u04ff]+$")
WORD_TOKEN_PATTERN = re.compile(r"\b\w+\b")
LATIN_CHAR_PATTERN = re.compile(r"[a-zA-Z]")


@dataclass(frozen=True)
class RatioResult:
    """Результаты подсчета русскоязычных слов и латинских символов."""

    ratio: float
    russian_words: int
    total_words: int
    latin_chars: int


def count_latin_characters(text: str) -> int:
    """Подсчитывает количество латинских символов в тексте."""
    return len(LATIN_CHAR_PATTERN.findall(text))


def russian_word_ratio(input_data: str | Sequence[Any]) -> RatioResult:
    """Вычисляет долю русских слов среди всех словесных токенов.

    Принимает строку либо последовательность сегментов (объектов с атрибутом .text или словарей).
    Пустые сегменты пропускаются и не вызывают деления на ноль.
    Токены длиной < 2 и чисто числовые токены игнорируются.
    """
    if isinstance(input_data, str):
        texts = [input_data]
    else:
        texts = []
        for item in input_data:
            if isinstance(item, str):
                texts.append(item)
            elif hasattr(item, "text"):
                texts.append(getattr(item, "text", ""))
            elif isinstance(item, dict) and "text" in item:
                texts.append(str(item["text"]))

    total_russian = 0
    total_words = 0
    total_latin_chars = 0

    for text in texts:
        if not text.strip():
            continue

        total_latin_chars += count_latin_characters(text)
        tokens = WORD_TOKEN_PATTERN.findall(text)

        for token in tokens:
            # Исключаем токены длиной меньше 2 символов
            if len(token) < 2:
                continue

            # Исключаем чисто числовые токены
            if not any(c.isalpha() for c in token):
                continue

            normalized = token.lower().replace("ё", "е")
            total_words += 1

            if CYRILLIC_PATTERN.match(normalized):
                total_russian += 1

    ratio = (total_russian / total_words) if total_words > 0 else 1.0
    return RatioResult(
        ratio=round(ratio, 3),
        russian_words=total_russian,
        total_words=total_words,
        latin_chars=total_latin_chars,
    )

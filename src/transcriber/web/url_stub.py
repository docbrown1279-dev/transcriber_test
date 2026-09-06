"""Заглушка классификатора ссылок YouTube / Яндекс Диск. Загрузка по URL не выполняется."""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlparse

_YOUTUBE_HOST = re.compile(
    r"(^|\.)((youtube\.com)|(youtu\.be)|(youtube-nocookie\.com))$",
    re.IGNORECASE,
)
_YANDEX_HOST = re.compile(
    r"(^|\.)((disk\.yandex\.[a-z.]+)|(yadi\.sk)|(yandex\.[a-z.]+))$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class UrlClassification:
    """Результат разбора URL без сетевых запросов."""

    kind: str
    url: str
    message: str


def classify_media_url(url: str) -> UrlClassification:
    """Определяет тип ссылки: youtube, yandex или unknown. Ничего не скачивает."""
    raw = url.strip()
    if not raw:
        return UrlClassification(
            kind="empty",
            url=raw,
            message="Сейчас принимается только файл.",
        )
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.hostname or "").lower()
    if _YOUTUBE_HOST.search(host) or "youtu.be" in host:
        kind = "youtube"
    elif _YANDEX_HOST.search(host) or "yadi.sk" in host:
        kind = "yandex"
    else:
        kind = "unknown"
    return UrlClassification(
        kind=kind,
        url=raw,
        message="Загрузка по ссылке ещё не реализована. Приложите аудиофайл.",
    )

"""Реестр заменяемых компонентов и движков конвейера.

Служит фабрикой компонентов на основе профилей конфигурации.
Все зарегистрированные компоненты, еще не реализованные на текущем этапе,
вызывают StageNotImplementedError или ComponentUnavailableError.
"""

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

from transcriber.errors import (
    ComponentUnavailableError,
    StageNotImplementedError,
    UnknownComponentError,
)


@dataclass(frozen=True)
class RegistryEntry:
    """Запись реестра с фабрикой и поддерживаемыми профилями."""

    area: str
    key: str
    factory: Callable[[], Any]
    profiles: tuple[str, ...]


_REGISTRY: dict[str, dict[str, RegistryEntry]] = {}


def register(
    area: str,
    key: str,
    factory: Callable[[], Any],
    profiles: Sequence[str],
) -> None:
    """Регистрирует фабрику компонента для заданной области и списка профилей."""
    if area not in _REGISTRY:
        _REGISTRY[area] = {}
    _REGISTRY[area][key] = RegistryEntry(
        area=area,
        key=key,
        factory=factory,
        profiles=tuple(profiles),
    )


def build(area: str, key: str, profile: str = "demo") -> Any:
    """Создает экземпляр компонента по имени области, ключу и профилю.

    Вызывает UnknownComponentError, если ключ не зарегистрирован,
    ComponentUnavailableError, если ключ не поддерживается в профиле,
    или StageNotImplementedError, если компонент запланирован на следующий этап.
    """
    if area not in _REGISTRY or key not in _REGISTRY[area]:
        raise UnknownComponentError(area=area, key=key)

    entry = _REGISTRY[area][key]
    if profile not in entry.profiles:
        supported = ", ".join(sorted(entry.profiles))
        hint = f"Component is available in profiles: {supported}"
        raise ComponentUnavailableError(component=key, profile=profile, hint=hint)

    return entry.factory()


def available(area: str, profile: str) -> list[str]:
    """Возвращает список доступных ключей компонентов для указанной области и профиля."""
    if area not in _REGISTRY:
        return []
    return [key for key, entry in _REGISTRY[area].items() if profile in entry.profiles]


def _make_stub_factory(area: str, key: str) -> Callable[[], Any]:
    """Создает заглушку фабрики, возбуждающую StageNotImplementedError при вызове."""

    def stub() -> Any:
        raise StageNotImplementedError(stage=f"{area}:{key}")

    return stub


# Регистрация всех компонентов согласно контракту module_interfaces.md §3
_CONTRACT_COMPONENTS: list[tuple[str, str, tuple[str, ...]]] = [
    # vad
    ("vad", "silero", ("demo", "dev", "prod")),
    ("vad", "ten_fallback", ("dev", "prod")),
    ("vad", "disabled", ("dev",)),
    # diarization
    ("diarization", "wespeaker_onnx", ("demo", "dev", "prod")),
    ("diarization", "pyannote31", ("dev", "prod")),
    # asr
    ("asr", "gigaam_v3_rnnt", ("demo", "dev", "prod")),
    ("asr", "gigaam_e2e_rnnt", ("dev",)),
    # correction
    ("correction", "dictionary_suggest", ("demo", "dev", "prod")),
    ("correction", "domain_dictionaries", ("prod",)),
    # embeddings
    ("embeddings", "rubert_tiny2", ("demo", "dev", "prod")),
    ("embeddings", "bge_small_onnx", ("dev", "prod")),
    ("embeddings", "jina_v3", ("dev", "prod")),
    # chunking
    ("chunking", "packing_c", ("demo", "dev", "prod")),
    ("chunking", "late_chunking_jina", ("dev", "prod")),
    ("chunking", "hybrid_c_then_d", ("dev",)),
    # llm
    ("llm", "gemini", ("demo", "dev")),
    ("llm", "local_llama", ("dev", "prod")),
    ("llm", "openai_compat", ("dev", "prod")),
    # export
    ("export", "json", ("demo", "dev", "prod")),
    ("export", "markdown", ("demo", "dev", "prod")),
    ("export", "pdf", ("prod",)),
]

for _area, _key, _profiles in _CONTRACT_COMPONENTS:
    register(_area, _key, _make_stub_factory(_area, _key), _profiles)

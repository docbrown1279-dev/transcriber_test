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


# Реальные фабрики для компонентов этапа D1
def _build_silero_vad() -> Any:
    from transcriber.vad.silero import SileroVadDetector

    return SileroVadDetector()


def _build_disabled_vad() -> Any:
    from transcriber.vad.disabled import DisabledVadDetector

    return DisabledVadDetector()


def _build_wespeaker_diarizer() -> Any:
    from transcriber.diarization.wespeaker import WeSpeakerDiarizer

    return WeSpeakerDiarizer()


def _build_gigaam_asr() -> Any:
    from transcriber.asr.gigaam import GigaAmAsrEngine

    return GigaAmAsrEngine()


def _build_dictionary_suggester() -> Any:
    from transcriber.correction.dictionary_suggest import DictionaryTermSuggester

    return DictionaryTermSuggester()


# Регистрация всех компонентов согласно контракту module_interfaces.md §3
_CONTRACT_COMPONENTS: list[tuple[str, str, Callable[[], Any], tuple[str, ...]]] = [
    # vad
    ("vad", "silero", _build_silero_vad, ("demo", "dev", "prod")),
    ("vad", "ten_fallback", _make_stub_factory("vad", "ten_fallback"), ("dev", "prod")),
    ("vad", "disabled", _build_disabled_vad, ("dev",)),
    # diarization
    ("diarization", "wespeaker_onnx", _build_wespeaker_diarizer, ("demo", "dev", "prod")),
    ("diarization", "pyannote31", _make_stub_factory("diarization", "pyannote31"), ("dev", "prod")),
    # asr
    ("asr", "gigaam_v3_rnnt", _build_gigaam_asr, ("demo", "dev", "prod")),
    ("asr", "gigaam_e2e_rnnt", _make_stub_factory("asr", "gigaam_e2e_rnnt"), ("dev",)),
    # correction
    ("correction", "dictionary_suggest", _build_dictionary_suggester, ("demo", "dev", "prod")),
    (
        "correction",
        "domain_dictionaries",
        _make_stub_factory("correction", "domain_dictionaries"),
        ("prod",),
    ),
    # embeddings
    (
        "embeddings",
        "rubert_tiny2",
        _make_stub_factory("embeddings", "rubert_tiny2"),
        ("demo", "dev", "prod"),
    ),
    (
        "embeddings",
        "bge_small_onnx",
        _make_stub_factory("embeddings", "bge_small_onnx"),
        ("dev", "prod"),
    ),
    ("embeddings", "jina_v3", _make_stub_factory("embeddings", "jina_v3"), ("dev", "prod")),
    # chunking
    (
        "chunking",
        "packing_c",
        _make_stub_factory("chunking", "packing_c"),
        ("demo", "dev", "prod"),
    ),
    (
        "chunking",
        "late_chunking_jina",
        _make_stub_factory("chunking", "late_chunking_jina"),
        ("dev", "prod"),
    ),
    ("chunking", "hybrid_c_then_d", _make_stub_factory("chunking", "hybrid_c_then_d"), ("dev",)),
    # llm
    ("llm", "gemini", _make_stub_factory("llm", "gemini"), ("demo", "dev")),
    ("llm", "local_llama", _make_stub_factory("llm", "local_llama"), ("dev", "prod")),
    ("llm", "openai_compat", _make_stub_factory("llm", "openai_compat"), ("dev", "prod")),
    # export
    ("export", "json", _make_stub_factory("export", "json"), ("demo", "dev", "prod")),
    ("export", "markdown", _make_stub_factory("export", "markdown"), ("demo", "dev", "prod")),
    ("export", "pdf", _make_stub_factory("export", "pdf"), ("prod",)),
]

for _area, _key, _factory, _profiles in _CONTRACT_COMPONENTS:
    register(_area, _key, _factory, _profiles)

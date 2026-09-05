"""Тесты реестра заменяемых компонентов и политики заглушек."""

import pytest

from transcriber.errors import (
    ComponentUnavailableError,
    StageNotImplementedError,
    UnknownComponentError,
)
from transcriber.registry import available, build

EXPECTED_COMPONENTS: list[tuple[str, str]] = [
    ("vad", "silero"),
    ("vad", "ten_fallback"),
    ("vad", "disabled"),
    ("diarization", "wespeaker_onnx"),
    ("diarization", "pyannote31"),
    ("asr", "gigaam_v3_rnnt"),
    ("asr", "gigaam_e2e_rnnt"),
    ("correction", "dictionary_suggest"),
    ("correction", "domain_dictionaries"),
    ("embeddings", "rubert_tiny2"),
    ("embeddings", "bge_small_onnx"),
    ("embeddings", "jina_v3"),
    ("chunking", "packing_c"),
    ("chunking", "late_chunking_jina"),
    ("chunking", "hybrid_c_then_d"),
    ("llm", "gemini"),
    ("llm", "local_llama"),
    ("llm", "openai_compat"),
    ("export", "json"),
    ("export", "markdown"),
    ("export", "pdf"),
]


def test_d0_reg_01_all_contract_components_registered() -> None:
    """[D0-REG-01] every area/key pair from module_interfaces.md §3 is registered."""
    for area, key in EXPECTED_COMPONENTS:
        # Проверяем, что ключ известен реестру (не вызывает UnknownComponentError)
        try:
            build(area, key, profile="prod")
        except (ComponentUnavailableError, StageNotImplementedError):
            pass  # Зарегистрирован
        except UnknownComponentError:
            pytest.fail(f"Component '{key}' in area '{area}' is not registered")


def test_d0_reg_02_prod_only_keys_raise_in_demo() -> None:
    """[D0-REG-02] prod-only keys raise ComponentUnavailableError under demo, naming component, profile and hint."""
    prod_only = [
        ("diarization", "pyannote31"),
        ("chunking", "late_chunking_jina"),
        ("correction", "domain_dictionaries"),
        ("export", "pdf"),
        ("llm", "openai_compat"),
    ]
    for area, key in prod_only:
        with pytest.raises(ComponentUnavailableError) as exc_info:
            build(area, key, profile="demo")

        err = exc_info.value
        assert err.component == key
        assert err.profile == "demo"
        assert len(err.hint) > 0
        assert "profile" in err.hint.lower() or "available" in err.hint.lower()


def test_d0_reg_03_allowed_demo_keys_raise_stage_not_implemented() -> None:
    """[D0-REG-03] keys allowed in demo but arriving later raise StageNotImplementedError."""
    demo_keys = [
        ("vad", "silero"),
        ("diarization", "wespeaker_onnx"),
        ("asr", "gigaam_v3_rnnt"),
        ("correction", "dictionary_suggest"),
        ("embeddings", "rubert_tiny2"),
        ("chunking", "packing_c"),
        ("llm", "gemini"),
    ]
    for area, key in demo_keys:
        with pytest.raises(StageNotImplementedError):
            build(area, key, profile="demo")


def test_d0_reg_04_unknown_key_and_availability() -> None:
    """[D0-REG-04] unknown key raises UnknownComponentError; available('llm', 'demo') contains gemini and excludes local_llama."""
    with pytest.raises(UnknownComponentError) as exc_info:
        build("llm", "nonexistent_model", profile="demo")
    assert exc_info.value.key == "nonexistent_model"

    avail_llm = available("llm", "demo")
    assert "gemini" in avail_llm
    assert "local_llama" not in avail_llm

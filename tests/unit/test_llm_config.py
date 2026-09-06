"""D3 layered LLM configuration tests."""

import pytest

from transcriber.config.loader import load_config
from transcriber.errors import ComponentUnavailableError
from transcriber.llm.gemini import GeminiLlmClient
from transcriber.llm.factory import OpenAiCompatLlmClient, resolve_call_options
from transcriber.registry import available, build


def test_d3_cfg_01_demo_loads_backend_and_env_name() -> None:
    """[D3-CFG-01] Demo loads Gemini configuration without storing a key value."""
    cfg = load_config("demo")
    assert cfg.llm.backend == "gemini"
    assert cfg.llm.active_backend.api_key_env == "GEMINI_API_KEY"
    assert cfg.llm.active_backend.api_key_env.endswith("_API_KEY")


def test_d3_cfg_02_api_backends_select_openai_compat() -> None:
    """[D3-CFG-02] NVIDIA and Qwen carry OpenAI-compatible URLs."""
    cfg = load_config("demo")
    for backend_name in ("nvidia", "qwen"):
        cfg.llm.backend = backend_name
        backend = cfg.llm.active_backend
        assert backend.client == "openai_compat"
        assert backend.base_url is not None
        from transcriber.llm.factory import make_client

        assert isinstance(make_client(cfg.llm), OpenAiCompatLlmClient)


def test_d3_cfg_03_task_generation_values_override_base() -> None:
    """[D3-CFG-03] Task token limits override shared defaults."""
    cfg = load_config("demo")
    task = cfg.llm.tasks.meeting_insights.report
    options = resolve_call_options(cfg.llm, task)
    assert options.max_tokens == task.max_tokens == 3072
    assert options.temperature == cfg.llm.base_llm.temperature
    assert "extra_config" not in task.model_fields


def test_d3_reg_01_api_clients_build_while_local_stays_unavailable() -> None:
    """[D3-REG-01] Demo constructs API transports while local Llama stays unavailable."""
    assert isinstance(build("llm", "gemini", "demo"), GeminiLlmClient)
    assert isinstance(
        build("llm", "openai_compat", "demo"), OpenAiCompatLlmClient
    )
    with pytest.raises(ComponentUnavailableError):
        build("llm", "local_llama", "demo")


def test_d3_reg_02_demo_availability_includes_openai_transport() -> None:
    """[D3-REG-02] Demo lists OpenAI compatibility but excludes local Llama."""
    clients = available("llm", "demo")
    assert "openai_compat" in clients
    assert "local_llama" not in clients

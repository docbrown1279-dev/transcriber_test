"""D3 layered LLM configuration tests."""

from pathlib import Path

import pytest

from transcriber.config.loader import load_config
from transcriber.errors import ComponentUnavailableError
from transcriber.llm.factory import (
    OpenAiCompatLlmClient,
    load_backend_extra,
    make_client,
    resolve_call_options,
)
from transcriber.llm.gemini import GeminiLlmClient
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
        assert isinstance(make_client(cfg.llm), OpenAiCompatLlmClient)


def test_d3_cfg_03_task_generation_values_override_base() -> None:
    """[D3-CFG-03] Task token limits override shared defaults."""
    cfg = load_config("demo")
    extract_task = cfg.llm.tasks.meeting_insights.extract
    report_task = cfg.llm.tasks.meeting_insights.report
    extract_options = resolve_call_options(cfg.llm, extract_task)
    report_options = resolve_call_options(cfg.llm, report_task)
    assert extract_options.max_tokens == extract_task.max_tokens == 4096
    assert report_options.max_tokens == report_task.max_tokens == 4096
    assert extract_options.temperature == cfg.llm.base_llm.temperature
    assert "extra_config" not in type(extract_task).model_fields


def test_d3_cfg_04_backend_extra_config_merges_into_call_options(
    tmp_path: Path,
) -> None:
    """[D3-CFG-04] Backend extra_config can null temperature and add provider-only keys."""
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "profiles").mkdir()
    for name in ("base.yaml", "base_llm.yaml"):
        (config_root / name).write_text(
            Path("config").joinpath(name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (config_root / "profiles" / "demo.yaml").write_text(
        Path("config/profiles/demo.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (config_root / "llm_extra").mkdir()
    (config_root / "llm_extra" / "nvidia_extra.yaml").write_text(
        "temperature: null\nreasoning_effort: medium\n",
        encoding="utf-8",
    )
    loaded = load_config("demo", config_dir=config_root)
    loaded.llm.backend = "nvidia"
    loaded.llm.backends["nvidia"].extra_config = "llm_extra/nvidia_extra.yaml"
    options = resolve_call_options(
        loaded.llm,
        loaded.llm.tasks.meeting_insights.extract,
        config_dir=config_root,
    )
    assert options.temperature is None
    assert options.extra == {"reasoning_effort": "medium"}
    assert load_backend_extra(loaded.llm, config_dir=config_root)["reasoning_effort"] == "medium"


def test_d3_cfg_05_dotenv_fills_missing_env_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """[D3-CFG-05] `.env` fills unset variables and does not override existing ones."""
    monkeypatch.delenv("D3_TEST_DOTENV_KEY", raising=False)
    monkeypatch.setenv("D3_TEST_EXISTING_KEY", "from-environ")
    env_file = tmp_path / ".env"
    env_file.write_text(
        "D3_TEST_DOTENV_KEY=from-dotenv\nD3_TEST_EXISTING_KEY=from-dotenv-should-lose\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    config_root = tmp_path / "config"
    config_root.mkdir()
    (config_root / "profiles").mkdir()
    repo_config = Path("/work/speech_rec_test/config")
    for name in ("base.yaml", "base_llm.yaml"):
        (config_root / name).write_text(
            repo_config.joinpath(name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    (config_root / "profiles" / "demo.yaml").write_text(
        "app:\n  profile: demo\n",
        encoding="utf-8",
    )
    load_config("demo", config_dir=config_root)
    import os

    assert os.environ.get("D3_TEST_DOTENV_KEY") == "from-dotenv"
    assert os.environ.get("D3_TEST_EXISTING_KEY") == "from-environ"


def test_d3_reg_01_api_clients_build_while_local_stays_unavailable() -> None:
    """[D3-REG-01] Demo constructs API transports while local Llama stays unavailable."""
    assert isinstance(build("llm", "gemini", "demo"), GeminiLlmClient)
    assert isinstance(build("llm", "openai_compat", "demo"), OpenAiCompatLlmClient)
    with pytest.raises(ComponentUnavailableError):
        build("llm", "local_llama", "demo")


def test_d3_reg_02_demo_availability_includes_openai_transport() -> None:
    """[D3-REG-02] Demo lists OpenAI compatibility but excludes local Llama."""
    clients = available("llm", "demo")
    assert "openai_compat" in clients
    assert "local_llama" not in clients

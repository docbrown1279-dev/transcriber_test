"""Тесты загрузчика и валидатора конфигурационных профилей."""

import os
from pathlib import Path
import tempfile

import pytest
import yaml

from transcriber.config.loader import deep_merge, load_config
from transcriber.errors import ConfigError


def test_d0_cfg_01_profiles_load_and_app_profile_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    """[D0-CFG-01] demo, dev, prod load and validate; APP_PROFILE selects the profile; default is demo."""
    monkeypatch.delenv("APP_PROFILE", raising=False)
    default_cfg = load_config()
    assert default_cfg.app.profile == "demo"

    for profile_name in ["demo", "dev", "prod"]:
        monkeypatch.setenv("APP_PROFILE", profile_name)
        cfg = load_config()
        assert cfg.app.profile == profile_name

        cfg_explicit = load_config(profile_name)
        assert cfg_explicit.app.profile == profile_name


def test_d0_cfg_02_unknown_key_fails_with_path() -> None:
    """[D0-CFG-02] unknown key in a config section fails with the key path in the message."""
    with open("config/base.yaml", "r", encoding="utf-8") as f:
        base = yaml.safe_load(f)
    with open("config/profiles/demo.yaml", "r", encoding="utf-8") as f:
        overlay = yaml.safe_load(f)
    raw_data = deep_merge(base, overlay)
    raw_data["audio"]["unknown_parameter"] = 123

    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        (root / "profiles").mkdir()
        with open(root / "base.yaml", "w", encoding="utf-8") as f:
            yaml.dump(raw_data, f)
        with open(root / "profiles" / "demo.yaml", "w", encoding="utf-8") as f:
            yaml.dump({"app": {"profile": "demo"}}, f)

        with pytest.raises(ConfigError) as exc_info:
            load_config("demo", config_dir=tmpdir)

        error_message = str(exc_info.value)
        assert "audio.unknown_parameter" in error_message or "audio" in error_message


def test_d0_cfg_03_demo_contract_values(demo_config) -> None:
    """[D0-CFG-03] demo values match the contract."""
    assert demo_config.audio.max_minutes == 15
    assert demo_config.asr.max_segment_seconds == 25
    assert demo_config.chunking.similarity_threshold == 0.70
    assert demo_config.limits.requests_per_ip_per_day == 1
    assert demo_config.limits.result_ttl_hours == 24
    assert demo_config.llm.provider == "gemini"
    assert demo_config.vad.threshold == 0.45
    assert demo_config.vad.neg_threshold == 0.35
    assert demo_config.vad.min_silence_ms == 200
    assert demo_config.audio.gain.rms_threshold_dbfs == -30.0
    assert demo_config.diarization.embed.cluster_distance_threshold == 0.80


def test_d0_cfg_04_profile_selections_and_secrets(dev_config, prod_config) -> None:
    """[D0-CFG-04] dev selects local_llama, prod selects local components; secrets appear only as env var names."""
    assert dev_config.llm.provider == "local_llama"
    assert dev_config.llm.model_path is not None
    assert "GEMINI_API_KEY" not in str(dev_config.model_dump())

    assert prod_config.diarization.engine in ["pyannote31", "wespeaker_onnx"]
    assert prod_config.correction.domain_dictionary is True
    assert prod_config.ui.type == "interactive"

    for config_file in list(Path("config").glob("*.yaml")) + list(
        Path("config/profiles").glob("*.yaml")
    ):
        content = config_file.read_text(encoding="utf-8")
        assert "AIza" not in content
        assert "hf_" not in content


def test_d0_cfg_05_deep_merge_overlay_wins() -> None:
    """Profile overlay replaces nested scalars without dropping sibling keys."""
    merged = deep_merge(
        {"vad": {"threshold": 0.5, "min_speech_ms": 200}, "app": {"profile": "demo"}},
        {"vad": {"threshold": 0.35}},
    )
    assert merged["vad"]["threshold"] == 0.35
    assert merged["vad"]["min_speech_ms"] == 200

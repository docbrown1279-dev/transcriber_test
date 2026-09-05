"""Тесты эндпоинта /healthz и механизмов самодиагностики."""

import os
from pathlib import Path

from fastapi.testclient import TestClient
import pytest

from transcriber.config.loader import load_config
from transcriber.web.app import app
from transcriber.web.health import run_self_check

client = TestClient(app)


def test_d0_hlt_01_healthz_healthy_environment() -> None:
    """[D0-HLT-01] GET /healthz returns 200 and lists per-component status when environment is sane."""
    os.environ["JOB_IP_SALT"] = "valid_salt"
    response = client.get("/healthz")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "components" in data
    assert "config" in data["components"]
    assert "registry" in data["components"]
    assert "storage" in data["components"]
    assert "tools" in data["components"]
    assert "env" in data["components"]


def test_d0_hlt_02_healthz_broken_component_returns_503(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """[D0-HLT-02] a broken component (unwritable storage root or missing env var) returns 503 naming that component."""
    # Случай 1: отсутствует обязательная переменная окружения
    monkeypatch.delenv("JOB_IP_SALT", raising=False)
    response = client.get("/healthz")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "unhealthy"
    assert "env" in data.get("failing_components", [])

    # Случай 2: недоступный storage_root
    monkeypatch.setenv("JOB_IP_SALT", "valid_salt")
    cfg = load_config("demo")
    # Подменяем storage_root на несуществующий недоступный системный каталог
    cfg.app.storage_root = "/root/forbidden_storage_path"
    is_healthy, components = run_self_check(cfg=cfg)
    assert not is_healthy
    assert components["storage"].status == "error"

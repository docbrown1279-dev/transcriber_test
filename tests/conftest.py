"""Общие фикстуры и хуки для тестового набора transcriber."""

import os
from pathlib import Path

import pytest

from transcriber.config.loader import load_config
from transcriber.config.schema import AppConfig


@pytest.fixture
def fixtures_dir() -> Path:
    """Возвращает путь к каталогу с упакованными входными данными."""
    path_str = os.environ.get("TRANSCRIBER_FIXTURES_DIR", "cloud_in/inputs")
    return Path(path_str).resolve()


@pytest.fixture
def tmp_job_dir(tmp_path: Path) -> Path:
    """Создает временный каталог для изоляции артефактов задачи."""
    job_dir = tmp_path / "jobs" / "job_test"
    job_dir.mkdir(parents=True, exist_ok=True)
    return job_dir


@pytest.fixture
def demo_config() -> AppConfig:
    """Возвращает валидированную конфигурацию профиля demo."""
    return load_config("demo")


@pytest.fixture
def dev_config() -> AppConfig:
    """Возвращает валидированную конфигурацию профиля dev."""
    return load_config("dev")


@pytest.fixture
def prod_config() -> AppConfig:
    """Возвращает валидированную конфигурацию профиля prod."""
    return load_config("prod")


@pytest.fixture(autouse=True)
def ensure_job_ip_salt() -> None:
    """Обеспечивает наличие соли хеширования IP в тестовом окружении."""
    if "JOB_IP_SALT" not in os.environ:
        os.environ["JOB_IP_SALT"] = "test_salt_secret_123"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Пропускает тесты с маркером requires_inputs, если каталог данных отсутствует."""
    fixtures_path = Path(os.environ.get("TRANSCRIBER_FIXTURES_DIR", "cloud_in/inputs")).resolve()
    skip_inputs = pytest.mark.skip(reason=f"Inputs directory not found: {fixtures_path}")

    for item in items:
        if "requires_inputs" in item.keywords and not fixtures_path.is_dir():
            item.add_marker(skip_inputs)

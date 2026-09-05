"""Тесты хранилища жизненного цикла задач и безопасного хеширования IP."""

import json
from pathlib import Path

import pytest

from transcriber.errors import PreflightError
from transcriber.jobs.store import (
    append_stage_event,
    create_job,
    get_job,
    hash_client_ip,
    update_job_state,
)
from transcriber.pipeline.events import StageEvent


def test_d0_job_01_lifecycle_state_transitions_and_events(tmp_path: Path) -> None:
    """[D0-JOB-01] job.json matches contract; state transitions queued->running->done; events append in order."""
    job_id = "test_lifecycle_job"
    raw_ip = "192.168.1.100"

    job = create_job(job_id, raw_ip, tmp_path)
    assert job.schema_version == "1"
    assert job.state == "queued"
    assert len(job.stages) == 0

    # Переход в running
    job_running = update_job_state(job_id, "running", tmp_path)
    assert job_running.state == "running"

    # Добавление событий стадий
    ev1 = StageEvent(stage="normalize", status="running", pct=50)
    ev2 = StageEvent(stage="normalize", status="done", pct=100, runtime_sec=1.5)
    ev3 = StageEvent(stage="vad", status="running", pct=10)

    append_stage_event(job_id, ev1, tmp_path)
    append_stage_event(job_id, ev2, tmp_path)
    append_stage_event(job_id, ev3, tmp_path)

    loaded_job = get_job(job_id, tmp_path)
    assert len(loaded_job.stages) == 2  # normalize (обновился) и vad
    assert loaded_job.stages[0].stage == "normalize"
    assert loaded_job.stages[0].status == "done"
    assert loaded_job.stages[0].pct == 100
    assert loaded_job.stages[1].stage == "vad"

    # Завершение задачи
    job_done = update_job_state(job_id, "done", tmp_path)
    assert job_done.state == "done"


def test_d0_job_02_raw_ip_never_stored_and_salt_required(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """[D0-JOB-02] raw client IP never appears in job.json or logs — only the salted hash; missing JOB_IP_SALT fails loudly."""
    raw_ip = "203.0.113.42"
    job_id = "test_ip_job"

    # При наличии соли
    monkeypatch.setenv("JOB_IP_SALT", "super_secret_salt")
    expected_hash = hash_client_ip(raw_ip)
    assert raw_ip not in expected_hash

    job = create_job(job_id, raw_ip, tmp_path)
    assert job.client_ip_hash == expected_hash

    # Проверяем содержимое файла на диске
    job_file = tmp_path / "jobs" / job_id / "job.json"
    raw_content = job_file.read_text(encoding="utf-8")
    assert raw_ip not in raw_content
    assert expected_hash in raw_content

    # При отсутствии соли должно падать с понятной ошибкой
    monkeypatch.delenv("JOB_IP_SALT", raising=False)
    with pytest.raises(PreflightError) as exc_info:
        hash_client_ip(raw_ip)
    assert "JOB_IP_SALT" in str(exc_info.value)

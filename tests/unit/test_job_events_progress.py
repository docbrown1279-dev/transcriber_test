"""Progress events prefer the latest running stage (not stuck prep)."""

from pathlib import Path

import pytest

from transcriber.jobs.queue import job_events_payload
from transcriber.jobs.store import append_stage_event, create_job, update_job_state
from transcriber.pipeline.events import StageEvent


def test_events_prefer_latest_running_stage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOB_IP_SALT", "test-salt")
    job_id = "prog1"
    create_job(job_id, "127.0.0.1", tmp_path)
    update_job_state(job_id, "running", tmp_path)
    append_stage_event(
        job_id,
        StageEvent(stage="normalize", status="running", pct=2, message="Подготовка аудио и VAD"),
        tmp_path,
    )
    append_stage_event(
        job_id,
        StageEvent(
            stage="diarize",
            status="running",
            pct=40,
            message="Диаризация: фрагмент 1 из 3",
            eta_sec=120,
        ),
        tmp_path,
    )
    payload = job_events_payload(job_id, tmp_path)
    assert payload["status_label"] == "Диаризация: фрагмент 1 из 3"
    assert payload["pct"] >= 40

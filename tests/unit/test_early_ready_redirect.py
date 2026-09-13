"""Early TOC / job flag state machine for progress → result redirect."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from transcriber.config.loader import load_config
from transcriber.jobs.queue import job_events_payload
from transcriber.jobs.store import (
    create_job,
    get_job,
    update_job_flags,
    update_job_state,
)
from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    dump_artifact,
)
from transcriber.web.app import app


def _write_minimal_chapters(job_dir: Path, job_id: str) -> None:
    art = ChaptersArtifact(
        schema_version="1",
        job_id=job_id,
        chunker="packing_c",
        embedding_model="rubert_tiny2",
        similarity_threshold=0.7,
        chapters=[
            ChapterItem(
                id="C01",
                title="Черновик",
                start=0.0,
                end=10.0,
                duration_sec=10.0,
                source_ids=["s0001"],
                speakers=["SPEAKER_00"],
            )
        ],
        metrics=ChapterMetrics(chapters_per_minute=1.0, short_chapters=0, long_chapters=0),
        runtime_sec=0.1,
    )
    dump_artifact(art, job_dir / "chapters.json")


def _patch_routes_cfg(monkeypatch: pytest.MonkeyPatch, storage: Path):
    cfg = load_config("demo").model_copy(deep=True)
    cfg.app.storage_root = str(storage)
    monkeypatch.setattr("transcriber.web.routes._cfg", lambda: cfg)
    monkeypatch.setattr("transcriber.web.routes.load_config", lambda *a, **k: cfg)
    return cfg


def test_events_early_ready_while_running_signals_redirect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOB_IP_SALT", "test-salt")
    job_id = "early1"
    create_job(job_id, "127.0.0.1", tmp_path)
    update_job_state(job_id, "running", tmp_path)
    update_job_flags(job_id, tmp_path, early_ready=True, speakers_finalized=False)
    payload = job_events_payload(job_id, tmp_path)
    assert payload["state"] == "running"
    assert payload["early_ready"] is True
    assert payload["speakers_finalized"] is False
    assert payload["early_ready"] or payload["state"] == "done"


def test_progress_page_redirects_when_early_ready_and_chapters(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOB_IP_SALT", "test-salt")
    storage = tmp_path / "var"
    storage.mkdir(parents=True, exist_ok=True)
    _patch_routes_cfg(monkeypatch, storage)

    job_id = "early_redir"
    create_job(job_id, "127.0.0.1", storage)
    update_job_state(job_id, "running", storage)
    update_job_flags(job_id, storage, early_ready=True, speakers_finalized=False)
    _write_minimal_chapters(storage / "jobs" / job_id, job_id)

    client = TestClient(app)
    resp = client.get(f"/jobs/{job_id}", follow_redirects=False)
    assert resp.status_code in {303, 307}
    assert resp.headers.get("location", "").endswith(f"/jobs/{job_id}/result")


def test_progress_stays_when_running_without_early_ready(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOB_IP_SALT", "test-salt")
    storage = tmp_path / "var"
    storage.mkdir(parents=True, exist_ok=True)
    _patch_routes_cfg(monkeypatch, storage)

    job_id = "no_early"
    create_job(job_id, "127.0.0.1", storage)
    update_job_state(job_id, "running", storage)
    assert get_job(job_id, storage).early_ready is False

    client = TestClient(app)
    resp = client.get(f"/jobs/{job_id}", follow_redirects=False)
    assert resp.status_code == 200
    assert "Обработка".encode("utf-8") in resp.content


def test_progress_stays_when_early_ready_but_no_chapters_yet(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flag alone is not enough — chapters.json must exist (server-side guard)."""
    monkeypatch.setenv("JOB_IP_SALT", "test-salt")
    storage = tmp_path / "var"
    storage.mkdir(parents=True, exist_ok=True)
    _patch_routes_cfg(monkeypatch, storage)

    job_id = "early_no_ch"
    create_job(job_id, "127.0.0.1", storage)
    update_job_state(job_id, "running", storage)
    update_job_flags(job_id, storage, early_ready=True, speakers_finalized=False)

    client = TestClient(app)
    resp = client.get(f"/jobs/{job_id}", follow_redirects=False)
    assert resp.status_code == 200

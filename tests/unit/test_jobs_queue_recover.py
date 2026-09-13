"""Startup recovery: leftover running jobs must not block new uploads."""

from pathlib import Path

import pytest

from transcriber.jobs.store import (
    create_job,
    get_job,
    recover_orphaned_running_jobs,
    update_job_state,
)


def test_recover_orphaned_running_jobs_marks_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """After restart, a disk ``running`` job becomes ``failed`` so admit can proceed."""
    monkeypatch.setenv("JOB_IP_SALT", "test-salt")
    create_job("orphan_running", "127.0.0.1", tmp_path)
    update_job_state("orphan_running", "running", tmp_path)
    create_job("already_done", "127.0.0.1", tmp_path)
    update_job_state("already_done", "done", tmp_path)

    recovered = recover_orphaned_running_jobs(tmp_path)

    assert recovered == ["orphan_running"]
    orphan = get_job("orphan_running", tmp_path)
    assert orphan.state == "failed"
    assert orphan.error is not None
    assert "перезапуска" in orphan.error
    assert any(s.stage == "worker" and s.status == "failed" for s in orphan.stages)
    assert get_job("already_done", tmp_path).state == "done"


def test_recover_noop_when_no_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("JOB_IP_SALT", "test-salt")
    create_job("queued_only", "127.0.0.1", tmp_path)
    assert recover_orphaned_running_jobs(tmp_path) == []
    assert get_job("queued_only", tmp_path).state == "queued"

"""Staging preload helpers."""

from pathlib import Path

import pytest

from transcriber.jobs.staging import (
    claim_staging_to_job,
    clear_staging,
    find_staging_file,
    new_staging_id,
    read_staging_meta,
    sweep_stale_staging,
    write_staging_meta,
)


def test_staging_claim_moves_file(tmp_path: Path) -> None:
    sid = new_staging_id()
    staged = find_staging_file(tmp_path, sid)
    assert staged is None
    write_staging_meta(
        tmp_path,
        sid,
        filename="clip.m4a",
        size_bytes=4,
        client_ip_hash="abc",
    )
    path = tmp_path / "staging" / sid / "upload.m4a"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"data")
    assert find_staging_file(tmp_path, sid) == path
    job_dir = tmp_path / "jobs" / "job1"
    dest = claim_staging_to_job(tmp_path, sid, job_dir, dest_name="upload.m4a")
    assert dest.is_file()
    assert dest.read_bytes() == b"data"
    assert find_staging_file(tmp_path, sid) is None
    assert read_staging_meta(tmp_path, sid) is None


def test_sweep_stale_staging(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import datetime, timedelta, timezone

    sid = new_staging_id()
    write_staging_meta(
        tmp_path,
        sid,
        filename="a.wav",
        size_bytes=1,
        client_ip_hash="x",
    )
    (tmp_path / "staging" / sid / "upload.wav").write_bytes(b"1")
    meta_path = tmp_path / "staging" / sid / "meta.json"
    old = (datetime.now(timezone.utc) - timedelta(hours=10)).isoformat()
    meta_path.write_text(
        '{"staging_id":"%s","filename":"a.wav","size_bytes":1,'
        '"client_ip_hash":"x","created_at":"%s"}\n' % (sid, old),
        encoding="utf-8",
    )
    removed = sweep_stale_staging(tmp_path, max_age_hours=6.0)
    assert sid in removed
    clear_staging(tmp_path, sid)  # noop

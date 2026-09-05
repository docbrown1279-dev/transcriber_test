"""Хранилище жизненного цикла задач и состояний этапов.

Управляет созданием, обновлением и сериализацией job.json.
Хеширует IP-адреса клиентов с солью JOB_IP_SALT без сохранения исходных IP.
"""

import hashlib
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from transcriber.errors import PreflightError
from transcriber.models.artifacts import (
    JobArtifact,
    JobStageState,
    dump_artifact,
    load_artifact,
)
from transcriber.pipeline.events import StageEvent


def hash_client_ip(client_ip: str) -> str:
    """Хеширует IP-адрес клиента с использованием обязательной соли JOB_IP_SALT."""
    salt = os.environ.get("JOB_IP_SALT")
    if not salt:
        raise PreflightError("JOB_IP_SALT environment variable is required to hash client IP")
    payload = f"{salt}:{client_ip}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def get_job_dir(job_id: str, storage_root: Path | str) -> Path:
    """Возвращает каталог конкретной задачи внутри корня хранилища."""
    return Path(storage_root) / "jobs" / job_id


def get_job_path(job_id: str, storage_root: Path | str) -> Path:
    """Возвращает путь к файлу job.json."""
    return get_job_dir(job_id, storage_root) / "job.json"


def create_job(
    job_id: str,
    client_ip: str,
    storage_root: Path | str,
    ttl_hours: int = 24,
) -> JobArtifact:
    """Создает новую запись задачи в состоянии 'queued' и сохраняет job.json."""
    client_hash = hash_client_ip(client_ip)
    now = datetime.now(timezone.utc)
    expires = now + timedelta(hours=ttl_hours)

    job = JobArtifact(
        schema_version="1",
        job_id=job_id,
        created_at=now.isoformat(),
        expires_at=expires.isoformat(),
        client_ip_hash=client_hash,
        state="queued",
        stages=[],
        error=None,
    )

    path = get_job_path(job_id, storage_root)
    dump_artifact(job, path)
    return job


def get_job(job_id: str, storage_root: Path | str) -> JobArtifact:
    """Загружает данные задачи из job.json."""
    path = get_job_path(job_id, storage_root)
    return load_artifact(path, JobArtifact)


def update_job_state(
    job_id: str,
    state: str,
    storage_root: Path | str,
    error: str | None = None,
) -> JobArtifact:
    """Обновляет состояние задачи (queued -> running -> done / failed)."""
    job = get_job(job_id, storage_root)
    job.state = state
    if error is not None:
        job.error = error
    path = get_job_path(job_id, storage_root)
    dump_artifact(job, path)
    return job


def append_stage_event(
    job_id: str,
    event: StageEvent,
    storage_root: Path | str,
) -> JobArtifact:
    """Добавляет или обновляет информацию о стадии в структуре задачи."""
    job = get_job(job_id, storage_root)

    updated = False
    for stage_info in job.stages:
        if stage_info.stage == event.stage:
            stage_info.status = event.status
            stage_info.pct = event.pct
            stage_info.runtime_sec = event.runtime_sec
            stage_info.message = event.message
            updated = True
            break

    if not updated:
        job.stages.append(
            JobStageState(
                stage=event.stage,
                status=event.status,
                pct=event.pct,
                runtime_sec=event.runtime_sec,
                message=event.message,
            )
        )

    path = get_job_path(job_id, storage_root)
    dump_artifact(job, path)
    return job

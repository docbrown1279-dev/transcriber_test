"""Хранилище жизненного цикла задач и состояний этапов.

Управляет созданием, обновлением и сериализацией job.json.
Хеширует IP-адреса клиентов с солью JOB_IP_SALT без сохранения исходных IP.
"""

from __future__ import annotations

import hashlib
import logging
import os
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone
from pathlib import Path

from transcriber.errors import PreflightError
from transcriber.models.artifacts import (
    JobArtifact,
    JobStageItem,
    dump_artifact,
    load_artifact,
)
from transcriber.pipeline.events import StageEvent

logger = logging.getLogger(__name__)


def _dump_job(job: JobArtifact, path: Path) -> None:
    """Атомарно пишет job.json (tmp + replace), чтобы воркер не читал частично записанный файл."""
    tmp_path = path.with_name(path.name + ".tmp")
    dump_artifact(job, tmp_path)
    tmp_path.replace(path)


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
    ttl_hours: int | None = 24,
) -> JobArtifact:
    """Создает новую запись задачи в состоянии 'queued' и сохраняет job.json."""
    client_hash = hash_client_ip(client_ip)
    now = datetime.now(timezone.utc)
    hours = ttl_hours if ttl_hours is not None else 24 * 365
    expires = now + timedelta(hours=hours)

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
    _dump_job(job, path)
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
    if state in {"done", "failed"} and not job.finished_at:
        job.finished_at = datetime.now(timezone.utc).isoformat()
    path = get_job_path(job_id, storage_root)
    _dump_job(job, path)
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
            stage_info.eta_sec = event.eta_sec
            stage_info.eta_total_sec = event.eta_total_sec
            updated = True
            break

    if not updated:
        job.stages.append(
            JobStageItem(
                stage=event.stage,
                status=event.status,
                pct=event.pct,
                runtime_sec=event.runtime_sec,
                message=event.message,
                eta_sec=event.eta_sec,
                eta_total_sec=event.eta_total_sec,
            )
        )

    path = get_job_path(job_id, storage_root)
    _dump_job(job, path)
    return job


def update_job_flags(
    job_id: str,
    storage_root: Path | str,
    *,
    early_ready: bool | None = None,
    speakers_finalized: bool | None = None,
) -> JobArtifact:
    """Updates TTFT early-publish / speaker-lock flags on job.json."""
    job = get_job(job_id, storage_root)
    if early_ready is not None:
        job.early_ready = early_ready
    if speakers_finalized is not None:
        job.speakers_finalized = speakers_finalized
    path = get_job_path(job_id, storage_root)
    _dump_job(job, path)
    return job


def job_exists(job_id: str, storage_root: Path | str) -> bool:
    """Проверяет наличие файла job.json."""
    return get_job_path(job_id, storage_root).is_file()


def iter_job_ids(storage_root: Path | str) -> Iterator[str]:
    """Перечисляет идентификаторы задач, у которых есть job.json."""
    jobs_root = Path(storage_root) / "jobs"
    if not jobs_root.is_dir():
        return
    for child in sorted(jobs_root.iterdir()):
        if child.is_dir() and (child / "job.json").is_file():
            yield child.name


def iter_jobs(storage_root: Path | str) -> Iterator[JobArtifact]:
    """Загружает валидные job.json; битые файлы пропускает без содержимого артефакта."""
    for job_id in iter_job_ids(storage_root):
        try:
            yield get_job(job_id, storage_root)
        except Exception:
            logger.warning("skipping unreadable job.json for job_id=%s", job_id)


# Shown when a running job is orphaned by process/container restart.
_ORPHAN_RUNNING_ERROR = (
    "Обработка прервана после перезапуска сервера. "
    "Если оглавление уже появилось — черновик сохранён; загрузите файл снова для полного прогона."
)


def recover_orphaned_running_jobs(storage_root: Path | str) -> list[str]:
    """Mark leftover ``running`` jobs as failed (no live worker after restart).

    Docker rebuild / crash leaves ``state=running`` on disk; ``max_concurrent_jobs``
    then blocks every new upload («фантомная задача»).
    """
    root = Path(storage_root)
    recovered: list[str] = []
    for job in list(iter_jobs(root)):
        if job.state != "running":
            continue
        update_job_state(
            job.job_id,
            "failed",
            root,
            error=_ORPHAN_RUNNING_ERROR,
        )
        append_stage_event(
            job.job_id,
            StageEvent(
                stage="worker",
                status="failed",
                pct=0,
                message=_ORPHAN_RUNNING_ERROR,
            ),
            root,
        )
        recovered.append(job.job_id)
        logger.warning(
            "orphaned running job recovered job_id=%s early_ready=%s",
            job.job_id,
            job.early_ready,
        )
    return recovered

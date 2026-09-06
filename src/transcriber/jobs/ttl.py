"""TTL-уборщик каталогов задач по `expires_at`."""

from __future__ import annotations

import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path

from transcriber.jobs.store import get_job_dir, iter_jobs, update_job_state

logger = logging.getLogger(__name__)


def _parse_iso(value: str) -> datetime:
    text = value.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _is_under_jobs_root(job_dir: Path, storage_root: Path) -> bool:
    jobs_root = (storage_root / "jobs").resolve()
    resolved = job_dir.resolve()
    return resolved == jobs_root or jobs_root in resolved.parents


def sweep_expired_jobs(
    storage_root: Path | str,
    *,
    now: datetime | None = None,
) -> list[str]:
    """Удаляет каталоги задач с `expires_at` <= now. Возвращает id удалённых задач."""
    root = Path(storage_root)
    moment = now or datetime.now(timezone.utc)
    removed: list[str] = []
    for job in list(iter_jobs(root)):
        expires = _parse_iso(job.expires_at)
        if expires > moment:
            continue
        try:
            update_job_state(job.job_id, "expired", root)
        except Exception:
            logger.warning("could not mark expired job_id=%s", job.job_id)
        if remove_job_directory(job.job_id, root):
            removed.append(job.job_id)
            logger.info("expired job removed job_id=%s", job.job_id)
    return removed


def remove_job_directory(job_id: str, storage_root: Path | str) -> bool:
    """Удаляет каталог задачи, если он лежит внутри `{storage_root}/jobs/`."""
    root = Path(storage_root)
    job_dir = get_job_dir(job_id, root)
    if not _is_under_jobs_root(job_dir, root):
        logger.warning("refusing to remove job dir outside storage job_id=%s", job_id)
        return False
    if not job_dir.exists():
        return False
    shutil.rmtree(job_dir, ignore_errors=False)
    return True

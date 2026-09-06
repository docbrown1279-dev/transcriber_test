"""Однопоточная очередь задач демо-веб-слоя."""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from transcriber.config.schema import AppConfig
from transcriber.jobs.store import (
    append_stage_event,
    get_job,
    get_job_dir,
    update_job_state,
)
from transcriber.jobs.ttl import sweep_expired_jobs
from transcriber.pipeline.events import StageEvent
from transcriber.pipeline.orchestrator import run_job
from transcriber.pipeline.steps import PIPELINE_STEPS
from transcriber.web.public_errors import (
    overall_progress_pct,
    processing_seconds,
    public_job_error,
)

logger = logging.getLogger(__name__)

WEB_UNTIL_STAGE = "titles"


class JobQueue:
    """Один воркер: поднимает queued-задачи, не превышая max_concurrent_jobs."""

    def __init__(
        self,
        storage_root: Path | str,
        cfg: AppConfig,
        *,
        until: str = WEB_UNTIL_STAGE,
        process_fn: Callable[[str], None] | None = None,
    ) -> None:
        self.storage_root = Path(storage_root)
        self.cfg = cfg
        self.until = until
        self._process_fn = process_fn
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        """Запускает фоновый поток воркера."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._loop,
                name="transcriber-job-worker",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout_sec: float = 2.0) -> None:
        """Сигнализирует воркеру остановиться."""
        self._stop.set()
        self._wake.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout_sec)

    def submit(self, job_id: str) -> None:
        """Будит воркер после постановки задачи в queued."""
        logger.info("job queued job_id=%s", job_id)
        self._wake.set()

    @property
    def lock(self) -> threading.Lock:
        """Замок допуска новой задачи (лимиты + create_job)."""
        return self._lock

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                sweep_expired_jobs(self.storage_root)
                job_id = self._next_queued_id()
                if job_id is None:
                    self._wake.wait(timeout=2.0)
                    self._wake.clear()
                    continue
                worker = self._process_fn or (
                    lambda jid: process_job(
                        jid,
                        storage_root=self.storage_root,
                        cfg=self.cfg,
                        until=self.until,
                    )
                )
                worker(job_id)
            except Exception:
                logger.exception("job worker iteration failed")
                time.sleep(0.5)

    def _next_queued_id(self) -> str | None:
        jobs_root = self.storage_root / "jobs"
        if not jobs_root.is_dir():
            return None
        for child in sorted(jobs_root.iterdir()):
            path = child / "job.json"
            if not path.is_file():
                continue
            try:
                job = get_job(child.name, self.storage_root)
            except Exception:
                logger.warning("skipping unreadable job.json job_id=%s", child.name)
                continue
            if job.state == "queued":
                return job.job_id
        return None


def find_job_audio(job_dir: Path) -> Path | None:
    """Ищет входной медиафайл задачи: input.* предпочтительнее upload.*."""
    inputs = sorted(job_dir.glob("input.*"))
    if inputs:
        return inputs[0]
    uploads = sorted(job_dir.glob("upload.*"))
    if uploads:
        return uploads[0]
    return None


def process_job(
    job_id: str,
    *,
    storage_root: Path | str,
    cfg: AppConfig,
    until: str = WEB_UNTIL_STAGE,
) -> None:
    """Запускает оркестратор для задачи и пишет StageEvent в job.json."""
    root = Path(storage_root)
    job_dir = get_job_dir(job_id, root)
    update_job_state(job_id, "running", root)
    source = find_job_audio(job_dir)

    def emit(event: StageEvent) -> None:
        append_stage_event(job_id, event, root)

    try:
        run_job(
            job_dir=job_dir,
            source_audio=source,
            until=until,
            cfg=cfg,
            events=emit,
        )
        update_job_state(job_id, "done", root)
        logger.info("job done job_id=%s", job_id)
    except Exception as exc:
        reason = f"{type(exc).__name__}: {exc}"
        if len(reason) > 240:
            reason = reason[:240]
        if _chapters_present(job_dir) and until == WEB_UNTIL_STAGE:
            append_stage_event(
                job_id,
                StageEvent(
                    stage="titles",
                    status="failed",
                    pct=0,
                    message=reason,
                ),
                root,
            )
            update_job_state(job_id, "done", root, error=f"titles:{reason}")
            logger.error("job done without titles job_id=%s err=%s", job_id, reason)
            return
        update_job_state(job_id, "failed", root, error=reason)
        logger.error("job failed job_id=%s err=%s", job_id, reason)


def _chapters_present(job_dir: Path) -> bool:
    from transcriber.models.artifacts import ChaptersArtifact, load_artifact

    path = job_dir / "chapters.json"
    if not path.is_file():
        return False
    try:
        load_artifact(path, ChaptersArtifact)
        return True
    except Exception:
        return False


def stage_names() -> list[str]:
    """Имена стадий конвейера (для страницы прогресса)."""
    return [step.stage for step in PIPELINE_STEPS]


def job_events_payload(job_id: str, storage_root: Path | str) -> dict[str, Any]:
    """JSON для polling `GET /jobs/{id}/events` (без технических ошибок во фронт)."""
    job = get_job(job_id, storage_root)
    total = len(stage_names()) + 1
    elapsed = processing_seconds(job)
    running = job.state in {"queued", "running"}
    return {
        "job_id": job.job_id,
        "state": job.state,
        "error": public_job_error(job.state, job.error),
        "pct": overall_progress_pct(job.stages, total, job.state),
        "elapsed_sec": elapsed,
        "elapsed_running": running,
        "created_at": job.created_at,
        "expires_at": job.expires_at,
    }

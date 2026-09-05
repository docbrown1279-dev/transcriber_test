"""Оркестратор конвейера обработки встреч.

Планирует выполнение стадий, проверяет валидность существующих артефактов
и вычисляет статус каждой стадии (done / pending / unavailable).
Управляет пошаговым выполнением задач (resumable pipeline execution).
"""

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

from transcriber.config.loader import load_config
from transcriber.config.schema import AppConfig
from transcriber.models.artifacts import ChaptersArtifact, TranscriptArtifact, load_artifact
from transcriber.pipeline.artifacts import JobArtifactPaths
from transcriber.pipeline.steps import PIPELINE_STEPS, StepDefinition
from transcriber.registry import available

StageStatus = Literal["done", "pending", "unavailable"]


@dataclass(frozen=True)
class StagePlan:
    """План выполнения отдельной стадии конвейера."""

    stage: str
    status: StageStatus
    produces: str


def _is_component_available(step: StepDefinition, cfg: AppConfig) -> bool:
    """Проверяет доступность движка компонента для стадии в активном профиле."""
    profile = cfg.app.profile
    if step.area == "audio":
        return True
    if step.area == "vad":
        return cfg.vad.engine in available("vad", profile)
    if step.area == "diarization":
        return cfg.diarization.engine in available("diarization", profile)
    if step.area == "asr":
        return cfg.asr.engine in available("asr", profile)
    if step.area == "correction":
        return "dictionary_suggest" in available("correction", profile)
    if step.area == "chunking":
        return cfg.chunking.chunker in available("chunking", profile)
    if step.area == "llm":
        return cfg.llm.provider in available("llm", profile)
    return False


def _has_valid_artifact(file_path: Path, model_cls: type) -> bool:
    """Проверяет наличие и валидность файла артефакта согласно модели."""
    if not file_path.is_file():
        return False
    try:
        load_artifact(file_path, model_cls)
        return True
    except Exception:
        return False


def _is_step_done(step: StepDefinition, paths: JobArtifactPaths) -> bool:
    artifact_file = paths.path(step.produces)
    if not _has_valid_artifact(artifact_file, step.model_cls):
        return False
    if step.stage == "titles":
        chapters = load_artifact(artifact_file, ChaptersArtifact)
        return all(chapter.title.strip() for chapter in chapters.chapters)
    return True


def plan_job(job_dir: Path | str, cfg: AppConfig | None = None) -> list[StagePlan]:
    """Формирует упорядоченный план стадий для задачи с текущими статусами.

    Если в задаче уже есть валидный transcript.json, стадии normalize..asr
    считаются выполненными (done). Невалидные артефакты не считаются выполненными.
    """
    resolved_cfg = cfg or load_config()
    paths = JobArtifactPaths(job_dir)
    transcript_valid = _has_valid_artifact(paths.transcript, TranscriptArtifact)

    plans: list[StagePlan] = []
    pre_asr_stages = {"normalize", "vad", "diarize", "asr"}

    for step in PIPELINE_STEPS:
        # Если transcript.json уже готов и валиден, все шаги до ASR включительно считаются done
        if transcript_valid and step.stage in pre_asr_stages:
            plans.append(StagePlan(stage=step.stage, status="done", produces=step.produces))
            continue

        is_done = _is_step_done(step, paths)

        if is_done:
            status: StageStatus = "done"
        else:
            is_avail = _is_component_available(step, resolved_cfg)
            status = "pending" if is_avail else "unavailable"

        plans.append(StagePlan(stage=step.stage, status=status, produces=step.produces))

    return plans


def run_stage(
    stage_name: str,
    job_dir: Path | str,
    cfg: AppConfig | None = None,
    source_audio: Path | str | None = None,
) -> Path:
    """Запускает конкретную стадию конвейера."""
    resolved_cfg = cfg or load_config()
    paths = JobArtifactPaths(job_dir)
    ctx = SimpleNamespace(
        job_id=paths.job_dir.name,
        job_dir=paths.job_dir,
        source_audio=Path(source_audio) if source_audio else None,
    )

    for step in PIPELINE_STEPS:
        if step.stage == stage_name:
            return step.run(ctx, resolved_cfg)

    raise ValueError(f"Unknown stage: {stage_name}")


def run_job(
    job_dir: Path | str,
    source_audio: Path | str | None = None,
    until: str = "correction_suggest",
    cfg: AppConfig | None = None,
) -> dict[str, Path]:
    """Последовательно выполняет конвейер задачи до указанной стадии.

    Пропускает стадии, чьи артефакты уже существуют и валидны (resumable).
    """
    resolved_cfg = cfg or load_config()
    job_path = Path(job_dir)
    job_path.mkdir(parents=True, exist_ok=True)
    paths = JobArtifactPaths(job_path)

    ctx = SimpleNamespace(
        job_id=job_path.name,
        job_dir=job_path,
        source_audio=Path(source_audio) if source_audio else None,
    )

    executed: dict[str, Path] = {}
    valid_stages = [s.stage for s in PIPELINE_STEPS]
    if until not in valid_stages:
        raise ValueError(f"Invalid 'until' stage '{until}'. Valid stages: {valid_stages}")

    for step in PIPELINE_STEPS:
        target_file = paths.path(step.produces)
        if _is_step_done(step, paths):
            executed[step.stage] = target_file
        else:
            produced_path = step.run(ctx, resolved_cfg)
            executed[step.stage] = produced_path

        if step.stage == until:
            break

    return executed

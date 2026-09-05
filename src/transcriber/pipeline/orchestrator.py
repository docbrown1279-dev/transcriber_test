"""Оркестратор конвейера обработки встреч.

Планирует выполнение стадий, проверяет валидность существующих артефактов
и вычисляет статус каждой стадии (done / pending / unavailable).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from transcriber.config.loader import load_config
from transcriber.config.schema import AppConfig
from transcriber.models.artifacts import TranscriptArtifact, load_artifact
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

        artifact_file = paths.path(step.produces)
        is_done = _has_valid_artifact(artifact_file, step.model_cls)

        if is_done:
            status: StageStatus = "done"
        else:
            is_avail = _is_component_available(step, resolved_cfg)
            status = "pending" if is_avail else "unavailable"

        plans.append(StagePlan(stage=step.stage, status=status, produces=step.produces))

    return plans


def run_stage(stage_name: str, job_dir: Path | str, cfg: AppConfig | None = None) -> Path:
    """Запускает конкретную стадию конвейера.

    На этапе D0 все нереализованные стадии возбуждают StageNotImplementedError.
    """
    resolved_cfg = cfg or load_config()
    paths = JobArtifactPaths(job_dir)

    for step in PIPELINE_STEPS:
        if step.stage == stage_name:
            # step.run возбуждает StageNotImplementedError в D0
            return step.run(paths, resolved_cfg)

    raise ValueError(f"Unknown stage: {stage_name}")

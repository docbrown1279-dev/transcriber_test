"""Модуль конвейера обработки встреч."""

from transcriber.pipeline.artifacts import JobArtifactPaths
from transcriber.pipeline.events import StageEvent
from transcriber.pipeline.orchestrator import StagePlan, StageStatus, plan_job, run_stage
from transcriber.pipeline.steps import PIPELINE_STEPS, PipelineStep, StepDefinition

__all__ = [
    "PIPELINE_STEPS",
    "JobArtifactPaths",
    "PipelineStep",
    "StageEvent",
    "StagePlan",
    "StageStatus",
    "StepDefinition",
    "plan_job",
    "run_stage",
]

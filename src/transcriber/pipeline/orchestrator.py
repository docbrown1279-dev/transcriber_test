"""Оркестратор конвейера обработки встреч.

Планирует выполнение стадий, проверяет валидность существующих артефактов
и вычисляет статус каждой стадии (done / pending / unavailable).
Управляет пошаговым выполнением задач (resumable pipeline execution).
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from time import monotonic
from types import SimpleNamespace
from typing import Literal
import logging

from transcriber.config.loader import load_config
from transcriber.config.schema import AppConfig
from transcriber.models.artifacts import ChaptersArtifact, TranscriptArtifact, load_artifact
from transcriber.pipeline.artifacts import JobArtifactPaths
from transcriber.pipeline.events import StageEvent
from transcriber.pipeline.steps import PIPELINE_STEPS, StepDefinition
from transcriber.registry import available

logger = logging.getLogger(__name__)

StageStatus = Literal["done", "pending", "unavailable"]
EventSink = Callable[[StageEvent], None]


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


def _emit(events: EventSink | None, event: StageEvent) -> None:
    if events is None:
        return
    events(event)


def run_job(
    job_dir: Path | str,
    source_audio: Path | str | None = None,
    until: str = "correction_suggest",
    cfg: AppConfig | None = None,
    events: EventSink | None = None,
) -> dict[str, Path]:
    """Последовательно выполняет конвейер задачи до указанной стадии.

    Пропускает стадии, чьи артефакты уже существуют и валидны (resumable).

    ``pipeline.toc_mode``:
    - ``b`` (default demo): after diarize, fuse ASR+chunk+titles via ``pipeline_b``
      when ``until`` is ``chunk`` / ``titles`` / insights / report.
    - ``a``: full ASR then batch titles (``llm.titles_mode=batch``).

    ``pipeline.ttft_split``: when true and duration ≥ 2× min_part_sec, run the
    pause-cut TTFT path (early chapters after part1). Short files keep this path.
    """
    resolved_cfg = cfg or load_config()
    if resolved_cfg.pipeline.toc_mode == "a":
        resolved_cfg = resolved_cfg.model_copy(deep=True)
        resolved_cfg.llm.titles_mode = "batch"

    job_path = Path(job_dir)
    job_path.mkdir(parents=True, exist_ok=True)
    paths = JobArtifactPaths(job_path)

    ctx = SimpleNamespace(
        job_id=job_path.name,
        job_dir=job_path,
        source_audio=Path(source_audio) if source_audio else None,
        events=events,
    )

    executed: dict[str, Path] = {}
    valid_stages = [s.stage for s in PIPELINE_STEPS]
    if until not in valid_stages:
        raise ValueError(f"Invalid 'until' stage '{until}'. Valid stages: {valid_stages}")

    # TTFT file-split branch (long files only)
    if resolved_cfg.pipeline.ttft_split:
        from transcriber.pipeline.ttft_split import run_ttft_split, should_run_ttft_split
        from transcriber.web.health import probe_audio_file

        src = Path(source_audio) if source_audio else None
        if src is None:
            for candidate in sorted(job_path.iterdir()):
                if (
                    candidate.is_file()
                    and candidate.suffix.lower()
                    in {".wav", ".m4a", ".mp3", ".ogg", ".flac", ".webm", ".mp4"}
                    and candidate.name not in {"normalized.wav", "vad_input.wav"}
                ):
                    src = candidate
                    break
        duration_sec = 0.0
        if src is not None and src.is_file():
            try:
                duration_sec = float(probe_audio_file(src)["duration_sec"])
            except Exception:
                duration_sec = 0.0
        if should_run_ttft_split(resolved_cfg, duration_sec):
            return run_ttft_split(
                job_path,
                resolved_cfg,
                source_audio=src,
                events=events,
                until=until,
            )
        logger.info(
            "ttft_split_skipped duration=%.1f min_part=%.1f job_id=%s",
            duration_sec,
            resolved_cfg.pipeline.ttft.min_part_sec,
            job_path.name,
        )

    fuse_b = resolved_cfg.pipeline.toc_mode == "b" and until in {
        "chunk",
        "titles",
        "insights_extract",
        "report",
    }

    transcript_valid = _has_valid_artifact(paths.transcript, TranscriptArtifact)
    pre_asr_stages = {"normalize", "vad", "diarize", "asr"}
    for step in PIPELINE_STEPS:
        if transcript_valid and step.stage in pre_asr_stages:
            executed[step.stage] = paths.transcript
            _emit(
                events,
                StageEvent(stage=step.stage, status="done", pct=100, message="resumed"),
            )
            if step.stage == until:
                break
            continue

        # Mode B: replace asr→titles with streaming pipeline (once)
        if fuse_b and step.stage == "asr":
            titles_done = _is_step_done(
                next(s for s in PIPELINE_STEPS if s.stage == "titles"),
                paths,
            )
            if not titles_done:
                _emit(events, StageEvent(stage="asr", status="running", pct=0))
                t0 = monotonic()
                from transcriber.pipeline.pipeline_b import run_pipeline_b

                run_pipeline_b(job_path, resolved_cfg)
                runtime = round(monotonic() - t0, 3)
                for fused in ("asr", "chunk", "titles"):
                    out = paths.path(
                        next(s.produces for s in PIPELINE_STEPS if s.stage == fused)
                    )
                    executed[fused] = out
                    _emit(
                        events,
                        StageEvent(
                            stage=fused,
                            status="done",
                            pct=100,
                            runtime_sec=runtime if fused == "asr" else None,
                            message="toc_mode=b",
                        ),
                    )
            else:
                for fused in ("asr", "chunk", "titles"):
                    executed[fused] = paths.path(
                        next(s.produces for s in PIPELINE_STEPS if s.stage == fused)
                    )
                    _emit(
                        events,
                        StageEvent(
                            stage=fused, status="done", pct=100, message="resumed"
                        ),
                    )
            if until in {"asr", "chunk", "titles"}:
                # still allow correction_suggest if until is later — fall through
                if until == "asr":
                    break
                # continue loop for correction when until is chunk/titles
                continue
            continue

        if fuse_b and step.stage in {"chunk", "titles"}:
            # already handled with asr fuse
            if step.stage not in executed:
                executed[step.stage] = paths.path(step.produces)
            if step.stage == until:
                break
            continue

        target_file = paths.path(step.produces)
        if _is_step_done(step, paths):
            executed[step.stage] = target_file
            _emit(
                events,
                StageEvent(stage=step.stage, status="done", pct=100, message="resumed"),
            )
        else:
            _emit(events, StageEvent(stage=step.stage, status="running", pct=0))
            t0 = monotonic()
            produced_path = step.run(ctx, resolved_cfg)
            executed[step.stage] = produced_path
            _emit(
                events,
                StageEvent(
                    stage=step.stage,
                    status="done",
                    pct=100,
                    runtime_sec=round(monotonic() - t0, 3),
                ),
            )

        if step.stage == until:
            break

    return executed

"""Интерфейс командной строки (CLI) приложения transcriber."""

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from transcriber.config.loader import load_config
from transcriber.models.artifacts import (
    AudioArtifact,
    ChaptersArtifact,
    InsightsArtifact,
    JobArtifact,
    QualityArtifact,
    ReportArtifact,
    SpeechArtifact,
    SuggestionsArtifact,
    TranscriptArtifact,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)
from transcriber.models.legacy import convert_legacy_transcript
from transcriber.pipeline.orchestrator import plan_job
from transcriber.web.health import probe_audio_file, run_self_check

app = typer.Typer(
    name="transcriber",
    help="Консольная утилита управления конвейером стенографирования встреч",
    no_args_is_help=True,
)

_FILENAME_MODEL_MAP: dict[str, type[Any]] = {
    "audio.json": AudioArtifact,
    "speech.json": SpeechArtifact,
    "turns.json": TurnsArtifact,
    "transcript.json": TranscriptArtifact,
    "quality.json": QualityArtifact,
    "suggestions.json": SuggestionsArtifact,
    "chapters.json": ChaptersArtifact,
    "insights.json": InsightsArtifact,
    "report.json": ReportArtifact,
    "job.json": JobArtifact,
}

_ALL_MODELS: list[type[Any]] = [
    AudioArtifact,
    SpeechArtifact,
    TurnsArtifact,
    TranscriptArtifact,
    QualityArtifact,
    SuggestionsArtifact,
    ChaptersArtifact,
    InsightsArtifact,
    ReportArtifact,
    JobArtifact,
]


def _detect_and_validate(path: Path) -> tuple[bool, str]:
    """Пытается определить тип артефакта и валидировать его."""
    if not path.is_file():
        return False, f"File does not exist: {path}"

    filename = path.name
    model_cls = _FILENAME_MODEL_MAP.get(filename)

    if model_cls is not None:
        try:
            load_artifact(path, model_cls)
            return True, f"Valid {model_cls.__name__}"
        except Exception as exc:
            return False, f"Validation error ({model_cls.__name__}): {exc}"

    # Если имя нестандартное, проверяем совпадение с любой из известных моделей
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
        except Exception as exc:
            return False, f"Invalid JSON: {exc}"

    for candidate in _ALL_MODELS:
        try:
            candidate.model_validate(data)
            return True, f"Valid {candidate.__name__}"
        except Exception:
            continue

    return False, "Does not match any known artifact schema"


@app.command("run")
def cmd_run(
    job: Annotated[
        Path, typer.Option("--job", "-j", help="Каталог задачи для сохранения артефактов")
    ],
    audio: Annotated[
        Path | None,
        typer.Option("--audio", "-a", help="Путь к исходному аудиофайлу"),
    ] = None,
    transcript: Annotated[
        Path | None,
        typer.Option("--transcript", "-t", help="Готовый transcript.json для возобновления"),
    ] = None,
    until: Annotated[
        str, typer.Option("--until", "-u", help="Стадия конвейера, до которой выполнять обработку")
    ] = "correction_suggest",
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Профиль конфигурации")
    ] = None,
) -> None:
    """Выполняет конвейер из аудио или возобновляет его из готовой стенограммы."""
    cfg = load_config(profile)
    from transcriber.pipeline.orchestrator import run_job

    try:
        if transcript is not None:
            seeded = load_artifact(transcript, TranscriptArtifact)
            job.mkdir(parents=True, exist_ok=True)
            dump_artifact(seeded, job / "transcript.json")
        executed = run_job(
            job_dir=job,
            source_audio=audio,
            until=until,
            cfg=cfg,
        )
        for stage, path in executed.items():
            typer.echo(f"Done: {stage} -> {path}")
    except Exception as exc:
        typer.echo(f"Job execution failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("plan")
def cmd_plan(
    job: Annotated[Path, typer.Option("--job", "-j", help="Каталог задачи с артефактами")],
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Профиль конфигурации")
    ] = None,
) -> None:
    """Выводит упорядоченный граф стадий конвейера с текущими статусами."""
    cfg = load_config(profile)
    plans = plan_job(job, cfg=cfg)

    for p in plans:
        typer.echo(f"{p.stage}: {p.status} ({p.produces})")


@app.command("validate")
def cmd_validate(
    paths: Annotated[
        list[Path], typer.Argument(help="Пути к файлам артефактов для проверки")
    ],
) -> None:
    """Валидирует файлы артефактов по схемам pydantic моделей."""
    failed = False
    for path in paths:
        is_valid, message = _detect_and_validate(path)
        if is_valid:
            typer.echo(f"OK: {path} - {message}")
        else:
            typer.echo(f"FAIL: {path} - {message}", err=True)
            failed = True

    if failed:
        raise typer.Exit(code=1)


@app.command("convert-legacy")
def cmd_convert_legacy(
    src: Annotated[
        Path, typer.Argument(help="Исходный файл стенограммы в исследовательском формате")
    ],
    dest: Annotated[
        Path, typer.Argument(help="Целевой файл канонического артефакта transcript.json")
    ],
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Профиль конфигурации")
    ] = None,
) -> None:
    """Конвертирует исследовательский JSON стенограммы в канонический TranscriptArtifact."""
    try:
        convert_legacy_transcript(src, dest)
        typer.echo(f"Converted {src} -> {dest}")
    except Exception as exc:
        typer.echo(f"Conversion failed: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("probe-audio")
def cmd_probe_audio(
    path: Annotated[Path, typer.Argument(help="Путь к аудиофайлу для проверки")],
) -> None:
    """Проверяет читаемость аудиофайла через ffprobe и возвращает длительность и размер."""
    try:
        info = probe_audio_file(path)
        typer.echo(json.dumps(info, indent=2))
    except Exception as exc:
        typer.echo(f"Probe failed for {path}: {exc}", err=True)
        raise typer.Exit(code=1) from exc


@app.command("healthcheck")
def cmd_healthcheck(
    profile: Annotated[
        str | None, typer.Option("--profile", "-p", help="Профиль конфигурации")
    ] = None,
) -> None:
    """Выполняет стартовую самодиагностику системы без запуска веб-сервера."""
    cfg = load_config(profile)
    is_healthy, components = run_self_check(cfg=cfg)

    for name, comp in components.items():
        details = f" ({comp.details})" if comp.details else ""
        error_msg = f" - {comp.message}" if comp.message else ""
        typer.echo(f"[{comp.status.upper()}] {name}{details}{error_msg}")

    if not is_healthy:
        typer.echo("Self-check FAILED", err=True)
        raise typer.Exit(code=1)

    typer.echo("Self-check PASSED")


if __name__ == "__main__":
    app()

"""Deterministic Markdown rendering for meeting reports."""

from __future__ import annotations

from pathlib import Path

from transcriber.models.artifacts import ReportArtifact, dump_artifact


def _timestamp(seconds: float) -> str:
    total = int(seconds)
    return f"{total // 60:02d}:{total % 60:02d}"


def render_report_markdown(report: ReportArtifact) -> str:
    """Преобразует JSON-протокол в читаемый Markdown без вызова LLM."""
    lines = ["# Черновик протокола встречи", ""]
    if report.draft_warning:
        lines.extend(
            [
                "> Черновик создан автоматически и требует проверки человеком.",
                "",
            ]
        )
    lines.extend(["## Краткое содержание", "", report.summary.strip(), ""])
    lines.extend(["## Ключевые моменты", ""])
    for moment in report.key_moments:
        lines.append(
            f"- [{_timestamp(moment.start)}–{_timestamp(moment.end)}] "
            f"{moment.text} ({moment.speaker}, {moment.chapter_id})"
        )
    lines.extend(["", "## Главы", ""])
    for chapter in report.chapters:
        lines.append(
            f"- [{_timestamp(chapter.start)}–{_timestamp(chapter.end)}] "
            f"{chapter.title} ({chapter.id})"
        )
    lines.extend(["", "## Спикеры", ""])
    for speaker in report.speakers:
        label = f" — {speaker.label}" if speaker.label else ""
        lines.append(f"- {speaker.id}{label}: {speaker.speech_sec:.3f} с")
    return "\n".join(lines).rstrip() + "\n"


class MarkdownExporter:
    """Сохраняет валидированный протокол в формате Markdown."""

    name = "markdown"

    def export(self, report: ReportArtifact, dest: Path) -> Path:
        """Записывает Markdown-представление протокола."""
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(render_report_markdown(report), encoding="utf-8")
        return dest


class JsonExporter:
    """Сохраняет валидированный протокол в каноническом JSON."""

    name = "json"

    def export(self, report: ReportArtifact, dest: Path) -> Path:
        """Записывает детерминированный JSON-протокол."""
        dump_artifact(report, dest)
        return dest

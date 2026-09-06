"""Clock provenance checks for hydrated D3 artifacts."""

from __future__ import annotations

from dataclasses import dataclass

from transcriber.models.artifacts import (
    ChaptersArtifact,
    InsightsArtifact,
    ReportArtifact,
    TranscriptArtifact,
)


@dataclass(frozen=True)
class ClockGateResult:
    """Результат проверки происхождения временных меток."""

    mismatches: tuple[str, ...]

    @property
    def passed(self) -> bool:
        """Возвращает true, если несовпадений нет."""
        return not self.mismatches


def clock_gate(
    insights: InsightsArtifact,
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    report: ReportArtifact | None = None,
) -> ClockGateResult:
    """Проверяет точное копирование времени из стенограммы и глав."""
    segments = {segment.id: segment for segment in transcript.segments}
    chapter_map = {chapter.id: chapter for chapter in chapters.chapters}
    mismatches: list[str] = []
    insight_sources: set[tuple[float, float, str, str]] = set()

    for insight in insights.chapters:
        chapter = chapter_map.get(insight.id)
        if chapter is None:
            mismatches.append(f"Unknown insight chapter {insight.id}")
        elif insight.start != chapter.start or insight.end != chapter.end:
            mismatches.append(f"Insight chapter bounds differ for {insight.id}")
        for item in insight.key_points + insight.actions + insight.open_questions:
            for source in item.src:
                segment = segments.get(source.segment_id)
                if segment is None:
                    mismatches.append(f"Unknown source segment {source.segment_id}")
                    continue
                if (
                    source.start != segment.start
                    or source.end != segment.end
                    or source.speaker != segment.speaker
                ):
                    mismatches.append(f"Source metadata differs for {source.segment_id}")
                insight_sources.add(
                    (source.start, source.end, source.speaker, insight.id)
                )

    if report is not None:
        for chapter_ref in report.chapters:
            chapter = chapter_map.get(chapter_ref.id)
            if chapter is None:
                mismatches.append(f"Unknown report chapter {chapter_ref.id}")
            elif (
                chapter_ref.start != chapter.start
                or chapter_ref.end != chapter.end
                or chapter_ref.title != chapter.title
            ):
                mismatches.append(f"Report chapter metadata differs for {chapter_ref.id}")
        for index, moment in enumerate(report.key_moments):
            key = (moment.start, moment.end, moment.speaker, moment.chapter_id)
            if key not in insight_sources:
                mismatches.append(f"Report key moment {index} lacks a matching insight source")

    return ClockGateResult(mismatches=tuple(mismatches))

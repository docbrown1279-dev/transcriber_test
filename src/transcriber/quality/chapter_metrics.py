"""Metrics for chapter density and duration warnings."""

from transcriber.models.artifacts import ChapterMetrics, ChaptersArtifact


def calculate_chapter_metrics(
    chapters: ChaptersArtifact,
    audio_sec: float,
    *,
    short_sec: float,
    long_sec: float,
) -> ChapterMetrics:
    """Пересчитывает плотность и счетчики длительности глав."""
    if audio_sec <= 0:
        raise ValueError("audio_sec must be positive")
    density = len(chapters.chapters) / (audio_sec / 60.0)
    return ChapterMetrics(
        chapters_per_minute=round(density, 3),
        short_chapters=sum(chapter.duration_sec < short_sec for chapter in chapters.chapters),
        long_chapters=sum(chapter.duration_sec > long_sec for chapter in chapters.chapters),
    )

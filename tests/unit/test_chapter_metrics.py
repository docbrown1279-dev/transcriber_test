"""Tests for chapter density and duration metrics."""

from transcriber.models.artifacts import ChapterItem, ChapterMetrics, ChaptersArtifact
from transcriber.quality.chapter_metrics import calculate_chapter_metrics


def _artifact(count: int) -> ChaptersArtifact:
    chapters = [
        ChapterItem(
            id=f"C{index:02d}",
            start=index * 60,
            end=(index + 1) * 60,
            source_ids=[f"s{index:04d}"],
            speakers=["A"],
            title=f"Глава {index}",
            duration_sec=60,
        )
        for index in range(count)
    ]
    return ChaptersArtifact(
        schema_version="1",
        job_id="job",
        chunker="packing_c",
        embedding_model="rubert_tiny2",
        similarity_threshold=0.7,
        chapters=chapters,
        metrics=ChapterMetrics(
            chapters_per_minute=0,
            short_chapters=0,
            long_chapters=0,
        ),
        runtime_sec=1,
    )


def test_d2_q_01_density_is_calculated_from_meeting_duration() -> None:
    """[D2-Q-01] Density inside the target band is retained exactly."""
    metrics = calculate_chapter_metrics(
        _artifact(6),
        600,
        short_sec=45,
        long_sec=180,
    )
    assert metrics.chapters_per_minute == 0.6
    assert metrics.short_chapters == 0
    assert metrics.long_chapters == 0

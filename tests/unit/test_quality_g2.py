"""Unit tests for reusable G2 quality checks."""

from transcriber.config.schema import AppConfig
from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    TranscriptArtifact,
    TranscriptSegment,
)
from transcriber.quality.checks import check_chapters


def _fixtures(chapter_count: int) -> tuple[TranscriptArtifact, ChaptersArtifact]:
    segments = [
        TranscriptSegment(
            id=f"s{index:04d}",
            turn_id=f"t{index:04d}",
            start=index * (600 / chapter_count),
            end=(index + 1) * (600 / chapter_count),
            speaker="A",
            text=f"содержательный текст главы номер {index}",
        )
        for index in range(chapter_count)
    ]
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job",
        engine="gigaam_v3_rnnt",
        segments=segments,
        max_segment_sec=200,
        runtime_sec=1,
    )
    chapters = [
        ChapterItem(
            id=f"C{index:02d}",
            start=segment.start,
            end=segment.end,
            source_ids=[segment.id],
            speakers=["A"],
            title=f"Тема главы {index}",
            duration_sec=segment.end - segment.start,
        )
        for index, segment in enumerate(segments)
    ]
    artifact = ChaptersArtifact(
        schema_version="1",
        job_id="job",
        chunker="packing_c",
        embedding_model="rubert_tiny2",
        similarity_threshold=0.7,
        chapters=chapters,
        metrics=ChapterMetrics(
            chapters_per_minute=chapter_count / 10,
            short_chapters=0,
            long_chapters=0,
        ),
        runtime_sec=1,
    )
    return transcript, artifact


def _status(report: object, check_id: str) -> str:
    return next(check.status for check in report.checks if check.id == check_id)  # type: ignore[attr-defined]


def test_d2_q_01_density_pass_warn_and_fail(demo_config: AppConfig) -> None:
    """[D2-Q-01] Density uses pass, warning, and failure bands from config."""
    transcript, chapters = _fixtures(6)
    assert _status(check_chapters(chapters, transcript, demo_config), "G2.2") == "pass"
    transcript, chapters = _fixtures(3)
    assert _status(check_chapters(chapters, transcript, demo_config), "G2.2") == "warn"
    transcript, chapters = _fixtures(2)
    assert _status(check_chapters(chapters, transcript, demo_config), "G2.2") == "fail"


def test_d2_q_02_title_constraints_fail(demo_config: AppConfig) -> None:
    """[D2-Q-02] Overlong and stamp-prefixed titles fail G2.4 and G2.5."""
    transcript, chapters = _fixtures(6)
    chapters.chapters[0].title = (
        "один два три четыре пять шесть семь восемь девять десять одиннадцать"
    )
    chapters.chapters[1].title = "Разговор о сетях"
    report = check_chapters(chapters, transcript, demo_config)
    assert _status(report, "G2.4") == "fail"
    assert _status(report, "G2.5") == "fail"


def test_d2_q_03_duplicate_and_empty_titles_fail(demo_config: AppConfig) -> None:
    """[D2-Q-03] Duplicate and empty titles fail G2.6."""
    transcript, chapters = _fixtures(6)
    chapters.chapters[0].title = ""
    chapters.chapters[2].title = chapters.chapters[1].title
    assert _status(check_chapters(chapters, transcript, demo_config), "G2.6") == "fail"


def test_d2_q_04_missing_or_overlapping_source_ids_fail(demo_config: AppConfig) -> None:
    """[D2-Q-04] Missing and overlapping non-empty source ids fail G2.7."""
    transcript, chapters = _fixtures(6)
    chapters.chapters[0].source_ids = [transcript.segments[1].id]
    assert _status(check_chapters(chapters, transcript, demo_config), "G2.7") == "fail"

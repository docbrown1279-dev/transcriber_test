"""D3 automated quality-gate tests."""

from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    InsightChapter,
    InsightSource,
    InsightsArtifact,
    KeyPoint,
    ReportArtifact,
    ReportChapterRef,
    ReportKeyMoment,
    TranscriptArtifact,
    TranscriptSegment,
)
from transcriber.quality.checks import check_insights, check_report


def _base() -> tuple[InsightsArtifact, ChaptersArtifact, TranscriptArtifact]:
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job",
        engine="fixture",
        segments=[
            TranscriptSegment(
                id="s1",
                turn_id="t1",
                start=1,
                end=2,
                speaker="A",
                text="срок 10 дней",
            )
        ],
        max_segment_sec=25,
        runtime_sec=0,
    )
    chapters = ChaptersArtifact(
        schema_version="1",
        job_id="job",
        chunker="packing_c",
        embedding_model="fixture",
        similarity_threshold=0.7,
        chapters=[
            ChapterItem(
                id="C00",
                start=1,
                end=2,
                source_ids=["s1"],
                speakers=["A"],
                title="Срок",
                duration_sec=1,
            )
        ],
        metrics=ChapterMetrics(
            chapters_per_minute=1,
            short_chapters=1,
            long_chapters=0,
        ),
        runtime_sec=0,
    )
    insights = InsightsArtifact(
        schema_version="1",
        job_id="job",
        provider="fixture",
        model="fixture",
        prompt_id="extract",
        chapters=[
            InsightChapter(
                id="C00",
                start=1,
                end=2,
                key_points=[
                    KeyPoint(
                        text="Срок 10 дней",
                        src=[
                            InsightSource(
                                segment_id="s1", start=1, end=2, speaker="A"
                            )
                        ],
                    )
                ],
            )
        ],
        llm_calls=1,
        runtime_sec=0,
    )
    return insights, chapters, transcript


def test_d3_q_01_missing_source_and_invented_digits_fail() -> None:
    """[D3-Q-01] Missing provenance and unseen digit groups fail."""
    insights, chapters, transcript = _base()
    insights.chapters[0].key_points = [
        KeyPoint.model_construct(text="Срок 99 дней", src=[])
    ]
    results = {item.id: item for item in check_insights(insights, chapters, transcript).checks}
    assert results["G3.3"].status == "fail"
    assert results["G3.4"].status == "fail"


def test_d3_q_02_stamp_prefix_fails() -> None:
    """[D3-Q-02] Stamp-prefixed key points and summaries fail."""
    insights, chapters, transcript = _base()
    insights.chapters[0].key_points[0].text = "Обсуждение срока"
    assert {c.id: c for c in check_insights(insights, chapters, transcript).checks}[
        "G3.7"
    ].status == "fail"


def test_d3_q_03_demo_requires_draft_warning() -> None:
    """[D3-Q-03] Demo reports must retain the draft warning."""
    insights, chapters, _ = _base()
    report = ReportArtifact(
        schema_version="1",
        job_id="job",
        summary="Срок подтверждён.",
        key_moments=[
            ReportKeyMoment(
                text="Срок 10 дней",
                start=1,
                end=2,
                speaker="A",
                chapter_id="C00",
            )
        ],
        chapters=[
            ReportChapterRef(id="C00", title="Срок", start=1, end=2)
        ],
        provider="fixture",
        model="fixture",
        llm_calls=1,
        draft_warning=False,
        runtime_sec=0,
    )
    assert {c.id: c for c in check_report(report, insights, chapters).checks}[
        "G3.8"
    ].status == "fail"

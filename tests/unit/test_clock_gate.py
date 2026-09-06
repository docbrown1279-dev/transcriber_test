"""D3 clock provenance tests."""

from transcriber.insights.clock_gate import clock_gate
from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    InsightChapter,
    InsightSource,
    InsightsArtifact,
    KeyPoint,
    TranscriptArtifact,
    TranscriptSegment,
)


def _artifacts(source_start: float) -> tuple[InsightsArtifact, ChaptersArtifact, TranscriptArtifact]:
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job",
        engine="fixture",
        segments=[
            TranscriptSegment(
                id="s1", turn_id="t1", start=1, end=2, speaker="A", text="факт"
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
                title="Факт",
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
                        text="Факт",
                        src=[
                            InsightSource(
                                segment_id="s1",
                                start=source_start,
                                end=2,
                                speaker="A",
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


def test_d3_clk_01_copied_times_pass_and_mismatch_fails() -> None:
    """[D3-CLK-01] Exact copied clocks pass while changed clocks fail."""
    assert clock_gate(*_artifacts(1)).passed
    assert not clock_gate(*_artifacts(1.5)).passed

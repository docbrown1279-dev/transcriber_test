"""D3 source hydration tests."""

from transcriber.insights.extract import ExtractItemPayload, filter_digit_verified_key_points, hydrate_items
from transcriber.models.artifacts import (
    ChapterItem,
    InsightSource,
    KeyPoint,
    TranscriptArtifact,
    TranscriptSegment,
)


def _inputs() -> tuple[ChapterItem, TranscriptArtifact]:
    chapter = ChapterItem(
        id="C00",
        start=1,
        end=2,
        source_ids=["s0001"],
        speakers=["A"],
        title="Сроки",
        duration_sec=1,
    )
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job",
        engine="fixture",
        segments=[
            TranscriptSegment(
                id="s0001",
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
    return chapter, transcript


def test_d3_hyd_01_segment_metadata_is_copied() -> None:
    """[D3-HYD-01] Hydration copies start, end, and speaker from the transcript."""
    chapter, transcript = _inputs()
    items, unknown = hydrate_items(
        [ExtractItemPayload(text="Срок 10 дней", segment_ids=["s0001"])],
        chapter,
        transcript,
        drop_unknown=False,
    )
    assert not unknown
    assert items[0].src[0].model_dump() == {
        "segment_id": "s0001",
        "start": 1.0,
        "end": 2.0,
        "speaker": "A",
    }


def test_d3_hyd_02_unknown_segment_writes_no_times() -> None:
    """[D3-HYD-02] Unknown ids are reported and never receive invented metadata."""
    chapter, transcript = _inputs()
    items, unknown = hydrate_items(
        [ExtractItemPayload(text="Неизвестно", segment_ids=["s9999"])],
        chapter,
        transcript,
        drop_unknown=True,
    )
    assert items == []
    assert unknown == ["s9999"]


def test_d3_hyd_03_digit_groups_must_match_chapter_text() -> None:
    """[D3-HYD-03] Key points with unverified digit groups are dropped."""
    verified = filter_digit_verified_key_points(
        [
            KeyPoint(
                text="Срок два три месяца",
                src=[
                    InsightSource(
                        segment_id="s0001",
                        start=1.0,
                        end=2.0,
                        speaker="A",
                    )
                ],
            ),
            KeyPoint(
                text="Срок 2-3 месяца",
                src=[
                    InsightSource(
                        segment_id="s0001",
                        start=1.0,
                        end=2.0,
                        speaker="A",
                    )
                ],
            ),
        ],
        "минимум два три месяца",
    )
    assert len(verified) == 1
    assert verified[0].text.startswith("Срок два")

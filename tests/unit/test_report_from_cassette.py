"""Offline D3 report generation and Markdown rendering tests."""

from pathlib import Path
from typing import Any

from transcriber.export.markdown import render_report_markdown
from transcriber.insights.report import generate_report
from transcriber.llm.base import LlmResponse
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


class CassetteClient:
    name = "cassette"

    def complete(
        self,
        prompt: str,
        *,
        prompt_id: str,
        max_tokens: int | None,
        temperature: float | None,
        json_schema: dict[str, Any] | None,
        extra: dict[str, object] | None = None,
    ) -> LlmResponse:
        assert '"segment_id": "s0001"' in prompt
        return LlmResponse(
            text=Path("tests/fixtures/llm/report_v1_sample.json").read_text(
                encoding="utf-8"
            ),
            provider=self.name,
            model="fixture",
            prompt_id=prompt_id,
            tokens_in=1,
            tokens_out=1,
            runtime_sec=0,
        )


def test_d3_cas_02_report_cassette_and_markdown(demo_config) -> None:
    """[D3-CAS-02] Report cassette yields five moments and renderer makes no LLM call."""
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
                text="срок согласования составляет 10 дней",
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
                source_ids=["s0001"],
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
                        text="Срок согласования составляет 10 дней",
                        src=[
                            InsightSource(
                                segment_id="s0001",
                                start=1,
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
    result = generate_report(
        insights, chapters, transcript, CassetteClient(), demo_config
    )
    assert len(result.key_moments) == 5
    assert result.speakers[0].label is None
    assert "Черновик протокола" in render_report_markdown(result)

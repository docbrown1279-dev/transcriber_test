"""Offline D3 extract test using a recorded response."""

from pathlib import Path
from typing import Any

from transcriber.insights.extract import extract_insights
from transcriber.llm.base import LlmResponse
from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
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
        assert "s0001 |" in prompt
        return LlmResponse(
            text=Path("tests/fixtures/llm/extract_v1_sample.json").read_text(
                encoding="utf-8"
            ),
            provider=self.name,
            model="fixture",
            prompt_id=prompt_id,
            tokens_in=1,
            tokens_out=1,
            runtime_sec=0,
        )


def test_d3_cas_01_extract_cassette_is_hydrated(demo_config) -> None:
    """[D3-CAS-01] Recorded extract output is hydrated from transcript metadata."""
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
    result = extract_insights(
        chapters, transcript, CassetteClient(), demo_config
    )
    assert result.chapters[0].key_points[0].src[0].start == 1
    assert result.llm_calls == 1

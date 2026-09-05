"""Offline title generation test using a recorded JSON response."""

from pathlib import Path

from transcriber.config.schema import AppConfig
from transcriber.llm.base import LlmResponse
from transcriber.llm.titles import apply_titles
from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    TranscriptArtifact,
    TranscriptSegment,
)


class CassetteClient:
    name = "cassette"

    def __init__(self, response_path: Path) -> None:
        self._response_path = response_path

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        temperature: float,
    ) -> LlmResponse:
        assert "инженерные сети" in prompt
        return LlmResponse(
            text=self._response_path.read_text(encoding="utf-8"),
            provider=self.name,
            model="fixture",
            prompt_id="title_p1_v1",
            tokens_in=1,
            tokens_out=1,
            runtime_sec=0,
        )


def test_d2_ttl_01_cassette_title_applied_and_extra_fields_ignored(
    demo_config: AppConfig,
) -> None:
    """[D2-TTL-01] Cassette title is applied while optional P1 fields stay out."""
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job",
        engine="gigaam_v3_rnnt",
        segments=[
            TranscriptSegment(
                id="s0001",
                turn_id="t0001",
                start=1,
                end=61,
                speaker="A",
                text="инженерные сети и подключение",
            )
        ],
        max_segment_sec=60,
        runtime_sec=1,
    )
    chapters = ChaptersArtifact(
        schema_version="1",
        job_id="job",
        chunker="packing_c",
        embedding_model="rubert_tiny2",
        similarity_threshold=0.7,
        chapters=[
            ChapterItem(
                id="C00",
                start=1,
                end=61,
                source_ids=["s0001"],
                speakers=["A"],
                title="",
                duration_sec=60,
            )
        ],
        metrics=ChapterMetrics(
            chapters_per_minute=1,
            short_chapters=0,
            long_chapters=0,
        ),
        runtime_sec=1,
    )
    cassette = Path("tests/fixtures/llm/title_p1_sample.json")
    titled, calls = apply_titles(chapters, transcript, CassetteClient(cassette), demo_config.llm)
    assert calls == 1
    assert titled.chapters[0].title == "Подключение инженерных сетей"
    assert set(titled.chapters[0].model_dump()) == {
        "id",
        "start",
        "end",
        "source_ids",
        "speakers",
        "title",
        "duration_sec",
    }

"""Contract tests for chapters.json."""

from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
)


def test_d2_art_01_minimal_chapters_artifact_round_trip() -> None:
    """[D2-ART-01] Minimal chapters artifact survives Pydantic round-trip."""
    artifact = ChaptersArtifact(
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
                title="Инженерные сети",
                duration_sec=60,
            )
        ],
        metrics=ChapterMetrics(
            chapters_per_minute=0.5,
            short_chapters=0,
            long_chapters=0,
        ),
        runtime_sec=1,
    )
    assert ChaptersArtifact.model_validate_json(artifact.model_dump_json()) == artifact

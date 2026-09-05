"""Unit tests for Stage D2 packing C."""

from typing import Any

import numpy as np

from transcriber.chunking.packing_c import (
    PackingCChunker,
    merge_similar_units,
    pack_speaker_pieces,
)
from transcriber.config.schema import ChunkingConfig
from transcriber.models.artifacts import TranscriptArtifact, TranscriptSegment


class FakeEmbedder:
    name = "fake"

    def __init__(self, vectors: list[list[float]]) -> None:
        self.vectors = np.asarray(vectors, dtype=float)

    def encode(self, texts: list[str]) -> np.ndarray[Any, Any]:
        assert len(texts) == len(self.vectors)
        return self.vectors


def _cfg() -> ChunkingConfig:
    return ChunkingConfig(
        packing_target_words=[4, 12],
        packing_max_gap_sec=2.0,
        similarity_threshold=0.7,
        merge_max_duration_sec=180,
        target_chapter_sec=[45, 180],
    )


def _segment(
    segment_id: str,
    start: float,
    end: float,
    speaker: str,
    text: str,
) -> TranscriptSegment:
    return TranscriptSegment(
        id=segment_id,
        turn_id=f"t{segment_id[1:]}",
        start=start,
        end=end,
        speaker=speaker,
        text=text,
        empty=not bool(text),
    )


def _transcript(segments: list[TranscriptSegment]) -> TranscriptArtifact:
    return TranscriptArtifact(
        schema_version="1",
        job_id="job",
        engine="gigaam_v3_rnnt",
        segments=segments,
        max_segment_sec=25,
        runtime_sec=1,
    )


def test_d2_pck_01_different_speakers_with_small_gap_are_packed() -> None:
    """[D2-PCK-01] Different speakers within the gap form one pack unit."""
    segments = [
        _segment("s0001", 1, 3, "A", "один два"),
        _segment("s0002", 4, 6, "B", "три четыре"),
    ]
    assert len(pack_speaker_pieces(segments, _cfg())) == 1


def test_d2_pck_02_large_gap_keeps_boundary() -> None:
    """[D2-PCK-02] A gap above the configured limit keeps a boundary."""
    segments = [
        _segment("s0001", 1, 3, "A", "один два"),
        _segment("s0002", 6, 8, "B", "три четыре"),
    ]
    assert len(pack_speaker_pieces(segments, _cfg())) == 2


def test_d2_pck_03_empty_segment_attaches_and_non_empty_coverage_is_complete() -> None:
    """[D2-PCK-03] Empty segments attach without losing non-empty source ids."""
    segments = [
        _segment("s0001", 1, 3, "A", "первый текст"),
        _segment("s0002", 3, 4, "B", ""),
        _segment("s0003", 4, 6, "A", "второй текст"),
    ]
    artifact = PackingCChunker().chunk(
        _transcript(segments),
        FakeEmbedder([[1, 0]]),
        _cfg(),
    )
    covered = [source_id for chapter in artifact.chapters for source_id in chapter.source_ids]
    assert covered == ["s0001", "s0002", "s0003"]


def test_d2_mrg_01_high_similarity_under_cap_merges() -> None:
    """[D2-MRG-01] Similar adjacent units merge below the duration cap."""
    units = pack_speaker_pieces(
        [
            _segment("s0001", 1, 3, "A", "один два три четыре"),
            _segment("s0002", 4, 6, "A", "пять шесть семь восемь"),
        ],
        _cfg(),
    )
    merged = merge_similar_units(units, np.asarray([[1, 0], [0.9, 0.1]]), _cfg())
    assert len(merged) == 1


def test_d2_mrg_02_low_similarity_and_duration_cap_keep_boundaries() -> None:
    """[D2-MRG-02] Low similarity and excessive duration independently block merging."""
    units = pack_speaker_pieces(
        [
            _segment("s0001", 1, 3, "A", "один два три четыре"),
            _segment("s0002", 4, 6, "A", "пять шесть семь восемь"),
        ],
        _cfg(),
    )
    assert len(merge_similar_units(units, np.asarray([[1, 0], [0, 1]]), _cfg())) == 2
    capped_cfg = _cfg().model_copy(update={"merge_max_duration_sec": 4})
    assert len(merge_similar_units(units, np.asarray([[1, 0], [1, 0]]), capped_cfg)) == 2


def test_d2_tim_01_chapter_times_equal_source_bounds() -> None:
    """[D2-TIM-01] Chapter boundaries exactly copy first and last segment times."""
    transcript = _transcript(
        [
            _segment("s0001", 1.125, 3.25, "A", "один два три четыре"),
            _segment("s0002", 4.5, 6.875, "A", "пять шесть семь восемь"),
        ]
    )
    artifact = PackingCChunker().chunk(
        transcript,
        FakeEmbedder([[1, 0], [1, 0]]),
        _cfg(),
    )
    assert artifact.chapters[0].start == transcript.segments[0].start
    assert artifact.chapters[0].end == transcript.segments[-1].end

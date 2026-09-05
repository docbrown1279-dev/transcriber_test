"""Speaker packing followed by adjacent semantic similarity merging."""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic

import numpy as np

from transcriber.chunking.base import EmbeddingBackend
from transcriber.config.schema import ChunkingConfig
from transcriber.models.artifacts import (
    ChapterItem,
    ChapterMetrics,
    ChaptersArtifact,
    TranscriptArtifact,
    TranscriptSegment,
)


@dataclass
class PackUnit:
    """Внутренний пакет последовательных сегментов стенограммы."""

    segments: list[TranscriptSegment]

    @property
    def text(self) -> str:
        return " ".join(segment.text.strip() for segment in self.segments if segment.text.strip())

    @property
    def word_count(self) -> int:
        return len(self.text.split())

    @property
    def start(self) -> float:
        return self.segments[0].start

    @property
    def end(self) -> float:
        return self.segments[-1].end

    @property
    def duration(self) -> float:
        return self.end - self.start


def _pieces_with_attached_empty_segments(
    segments: list[TranscriptSegment],
) -> list[PackUnit]:
    pieces: list[PackUnit] = []
    leading_empty: list[TranscriptSegment] = []
    for segment in segments:
        if segment.text.strip():
            piece_segments = [*leading_empty, segment]
            leading_empty.clear()
            pieces.append(PackUnit(piece_segments))
        elif pieces:
            pieces[-1].segments.append(segment)
        else:
            leading_empty.append(segment)
    if leading_empty:
        pieces.append(PackUnit(leading_empty))
    return pieces


def pack_speaker_pieces(
    segments: list[TranscriptSegment],
    cfg: ChunkingConfig,
) -> list[PackUnit]:
    """Пакует короткие соседние реплики разных спикеров в целевые блоки."""
    pieces = _pieces_with_attached_empty_segments(segments)
    if not pieces:
        return []

    target_min, target_max = cfg.packing_target_words
    packed: list[PackUnit] = [pieces[0]]
    for piece in pieces[1:]:
        current = packed[-1]
        gap = piece.start - current.end
        current_speaker = current.segments[-1].speaker
        next_speaker = piece.segments[0].speaker
        combined_words = current.word_count + piece.word_count
        cross_speaker_gap_ok = (
            current_speaker == next_speaker or gap <= cfg.packing_max_gap_sec
        )
        should_pack = (
            cross_speaker_gap_ok
            and current.word_count < target_min
            and combined_words <= target_max
        )
        if should_pack:
            current.segments.extend(piece.segments)
        else:
            packed.append(piece)
    return packed


def _cosine(left: np.ndarray, right: np.ndarray) -> float:
    denominator = float(np.linalg.norm(left) * np.linalg.norm(right))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(left, right) / denominator)


def merge_similar_units(
    units: list[PackUnit],
    vectors: np.ndarray,
    cfg: ChunkingConfig,
) -> list[PackUnit]:
    """Сливает соседние пакеты при достаточной косинусной близости."""
    if not units:
        return []
    if len(vectors) != len(units):
        raise ValueError("Embedding count must equal pack-unit count")

    merged: list[PackUnit] = [PackUnit(list(units[0].segments))]
    merged_vectors: list[np.ndarray] = [np.asarray(vectors[0], dtype=float)]
    merged_weights: list[int] = [max(units[0].word_count, 1)]

    for unit, raw_vector in zip(units[1:], vectors[1:], strict=True):
        current = merged[-1]
        vector = np.asarray(raw_vector, dtype=float)
        duration = unit.end - current.start
        similarity = _cosine(merged_vectors[-1], vector)
        can_merge = (
            similarity >= cfg.similarity_threshold
            and duration <= cfg.merge_max_duration_sec
            and duration <= cfg.target_chapter_sec[1]
        )
        if can_merge:
            weight = max(unit.word_count, 1)
            total_weight = merged_weights[-1] + weight
            combined = (
                merged_vectors[-1] * merged_weights[-1] + vector * weight
            ) / total_weight
            norm = np.linalg.norm(combined)
            merged_vectors[-1] = combined / norm if norm else combined
            merged_weights[-1] = total_weight
            current.segments.extend(unit.segments)
        else:
            merged.append(PackUnit(list(unit.segments)))
            merged_vectors.append(vector)
            merged_weights.append(max(unit.word_count, 1))
    return merged


class PackingCChunker:
    """Реализует packing C с семантическим слиянием соседних блоков."""

    name = "packing_c"

    def chunk(
        self,
        transcript: TranscriptArtifact,
        embedder: EmbeddingBackend,
        cfg: ChunkingConfig,
    ) -> ChaptersArtifact:
        """Создает главы, сохраняя исходные границы и идентификаторы сегментов."""
        started = monotonic()
        units = pack_speaker_pieces(transcript.segments, cfg)
        non_empty_units = [unit for unit in units if unit.text]
        if not non_empty_units:
            return ChaptersArtifact(
                schema_version=transcript.schema_version,
                job_id=transcript.job_id,
                chunker=self.name,
                embedding_model=embedder.name,
                similarity_threshold=cfg.similarity_threshold,
                chapters=[],
                metrics=ChapterMetrics(
                    chapters_per_minute=0.0,
                    short_chapters=0,
                    long_chapters=0,
                ),
                runtime_sec=round(monotonic() - started, 3),
            )

        vectors = embedder.encode([unit.text for unit in non_empty_units])
        merged = merge_similar_units(non_empty_units, vectors, cfg)
        chapters: list[ChapterItem] = []
        short_limit, long_limit = cfg.target_chapter_sec
        for index, unit in enumerate(merged):
            speakers = list(dict.fromkeys(segment.speaker for segment in unit.segments))
            duration = round(unit.duration, 3)
            chapters.append(
                ChapterItem(
                    id=f"C{index:02d}",
                    start=unit.start,
                    end=unit.end,
                    source_ids=[segment.id for segment in unit.segments],
                    speakers=speakers,
                    title="",
                    duration_sec=duration,
                )
            )

        meeting_minutes = max(segment.end for segment in transcript.segments) / 60.0
        density = len(chapters) / meeting_minutes if meeting_minutes else 0.0
        return ChaptersArtifact(
            schema_version=transcript.schema_version,
            job_id=transcript.job_id,
            chunker=self.name,
            embedding_model=embedder.name,
            similarity_threshold=cfg.similarity_threshold,
            chapters=chapters,
            metrics=ChapterMetrics(
                chapters_per_minute=round(density, 3),
                short_chapters=sum(chapter.duration_sec < short_limit for chapter in chapters),
                long_chapters=sum(chapter.duration_sec > long_limit for chapter in chapters),
            ),
            runtime_sec=round(monotonic() - started, 3),
        )

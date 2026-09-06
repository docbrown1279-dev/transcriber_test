"""Диаризация дикторов на базе WeSpeaker ResNet34 ONNX и кластеризации scikit-learn.

Рецепт выровнен с исследованием 1f / 1f2:
- Silero-регионы склеиваются gap ≤ vad_premerge_gap_sec **до** окон эмбеддинга;
- чанки короче min_embed_sec пропускаются;
- окна embed_window_sec / шаг embed_step_sec;
- AgglomerativeClustering(cosine, average, distance_threshold из config);
- после кластера — merge turns (gap / absorb) из контракта.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, cast

import numpy as np
import soundfile as sf
from sklearn.cluster import AgglomerativeClustering
from speakeronnx import SpeakerEmbedder

from transcriber.asr.holes import find_holes
from transcriber.config.schema import DiarizationConfig
from transcriber.diarization.base import Diarizer
from transcriber.diarization.merge import merge_turns
from transcriber.diarization.regions import Interval, merge_speech_regions
from transcriber.models.artifacts import (
    SpeechArtifact,
    TurnItem,
    TurnMergeInfo,
    TurnsArtifact,
    dump_artifact,
)


def _l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Построчная L2-нормализация эмбеддингов (устойчивый cosine)."""
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms = np.maximum(norms, 1e-12)
    return cast(np.ndarray[Any, Any], matrix / norms)


def _renumber_speakers(turns: list[TurnItem]) -> list[TurnItem]:
    """Перенумеровывает лейблы в плотный ряд SPEAKER_00… без дыр в id."""
    order: list[str] = []
    for turn in turns:
        if turn.speaker not in order:
            order.append(turn.speaker)
    mapping = {old: f"SPEAKER_{idx:02d}" for idx, old in enumerate(order)}
    return [
        TurnItem(id=t.id, start=t.start, end=t.end, speaker=mapping[t.speaker]) for t in turns
    ]


class WeSpeakerDiarizer(Diarizer):
    """Компонент диаризации на базе эмбеддингов WeSpeaker ResNet34 ONNX."""

    name: str = "wespeaker_onnx"

    def __init__(self, model_name: str = "wespeaker-resnet34") -> None:
        self._model_name = model_name
        self._embedder: SpeakerEmbedder | None = None

    def _get_embedder(self) -> SpeakerEmbedder:
        if self._embedder is None:
            self._embedder = SpeakerEmbedder(model=self._model_name)
        return self._embedder

    def diarize(
        self,
        wav: Path,
        speech: SpeechArtifact,
        cfg: DiarizationConfig,
        job_id: str | None = None,
    ) -> TurnsArtifact:
        """Разбивает речь на реплики дикторов, кластеризует и выполняет слияние."""
        t0 = time.time()
        wav_path = Path(wav)
        if not wav_path.is_file():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        resolved_job_id = job_id or wav_path.parent.name
        info = sf.info(str(wav_path))
        total_duration = round(float(info.duration), 3)

        if not speech.regions:
            artifact = TurnsArtifact(
                schema_version="1",
                job_id=resolved_job_id,
                diarizer="wespeaker_onnx",
                speaker_count=0,
                turns=[],
                holes=find_holes([], total_duration, cfg.merge.min_hole_sec),
                merge=TurnMergeInfo(
                    same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
                    absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
                ),
                runtime_sec=round(time.time() - t0, 3),
            )
            dump_artifact(artifact, wav_path.parent / "turns.json")
            return artifact

        audio, sr = sf.read(str(wav_path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        # 1f2: склейка VAD-фрагментов до окон; чанки < min_embed_sec — пропуск
        vad_intervals = [Interval(start=r.start, end=r.end) for r in speech.regions]
        speech_islands = merge_speech_regions(
            vad_intervals,
            max_gap_sec=cfg.merge.vad_premerge_gap_sec,
            min_duration_sec=cfg.embed.min_sec,
        )

        embedder = self._get_embedder()
        segments: list[tuple[float, float]] = []
        embeddings: list[np.ndarray] = []

        window_sec = cfg.embed.window_sec
        step_sec = cfg.embed.step_sec
        min_embed = cfg.embed.min_sec

        for island in speech_islands:
            dur = island.duration
            r_start_idx = int(island.start * sr)
            r_end_idx = int(island.end * sr)
            if r_end_idx <= r_start_idx:
                continue

            # Короткие острова — один эмбеддинг на весь интервал
            if dur <= window_sec + step_sec:
                slice_audio = audio[r_start_idx:r_end_idx]
                if len(slice_audio) < int(min_embed * sr):
                    continue
                emb = embedder.embed(slice_audio)
                segments.append((round(island.start, 3), round(island.end, 3)))
                embeddings.append(np.asarray(emb, dtype=np.float64))
                continue

            win_len = int(window_sec * sr)
            step_len = int(step_sec * sr)
            curr = r_start_idx
            while curr + win_len <= r_end_idx:
                emb = embedder.embed(audio[curr : curr + win_len])
                segments.append((round(curr / sr, 3), round((curr + win_len) / sr, 3)))
                embeddings.append(np.asarray(emb, dtype=np.float64))
                curr += step_len

            rem = r_end_idx - curr
            if rem >= int(min_embed * sr):
                emb = embedder.embed(audio[curr:r_end_idx])
                segments.append((round(curr / sr, 3), round(r_end_idx / sr, 3)))
                embeddings.append(np.asarray(emb, dtype=np.float64))

        if not embeddings:
            artifact = TurnsArtifact(
                schema_version="1",
                job_id=resolved_job_id,
                diarizer="wespeaker_onnx",
                speaker_count=0,
                turns=[],
                holes=find_holes([], total_duration, cfg.merge.min_hole_sec),
                merge=TurnMergeInfo(
                    same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
                    absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
                ),
                runtime_sec=round(time.time() - t0, 3),
            )
            dump_artifact(artifact, wav_path.parent / "turns.json")
            return artifact

        x = _l2_normalize(np.stack(embeddings))
        if len(x) == 1:
            labels = [0]
        else:
            clusterer = AgglomerativeClustering(
                metric="cosine",
                linkage="average",
                distance_threshold=cfg.embed.cluster_distance_threshold,
                n_clusters=None,
            )
            labels = clusterer.fit_predict(x).tolist()

        raw_turns: list[dict[str, Any]] = []
        for (start, end), lbl in zip(segments, labels, strict=True):
            raw_turns.append(
                {
                    "start": start,
                    "end": end,
                    "speaker": f"SPEAKER_{int(lbl):02d}",
                }
            )

        merged = merge_turns(
            raw_turns,
            same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
            absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
        )

        for i in range(len(merged) - 1):
            if merged[i].end > merged[i + 1].start:
                new_boundary = round(merged[i + 1].start, 3)
                if new_boundary > merged[i].start:
                    merged[i] = TurnItem(
                        id=merged[i].id,
                        start=merged[i].start,
                        end=new_boundary,
                        speaker=merged[i].speaker,
                    )

        merged = _renumber_speakers(merged)
        holes = find_holes(merged, total_duration, min_hole_sec=cfg.merge.min_hole_sec)
        unique_speakers = len({t.speaker for t in merged})

        artifact = TurnsArtifact(
            schema_version="1",
            job_id=resolved_job_id,
            diarizer="wespeaker_onnx",
            speaker_count=unique_speakers,
            turns=merged,
            holes=holes,
            merge=TurnMergeInfo(
                same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
                absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
            ),
            runtime_sec=round(time.time() - t0, 3),
        )
        dump_artifact(artifact, wav_path.parent / "turns.json")
        return artifact

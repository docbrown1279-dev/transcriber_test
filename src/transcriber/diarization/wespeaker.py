"""Диаризация дикторов на базе WeSpeaker ResNet34 ONNX и кластеризации scikit-learn."""

import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from sklearn.cluster import AgglomerativeClustering
from speakeronnx import SpeakerEmbedder

from transcriber.asr.holes import find_holes
from transcriber.config.schema import DiarizationConfig
from transcriber.diarization.base import Diarizer
from transcriber.diarization.merge import merge_turns
from transcriber.models.artifacts import (
    SpeechArtifact,
    TurnItem,
    TurnMergeInfo,
    TurnsArtifact,
    dump_artifact,
)


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
            holes = find_holes([], total_duration, cfg.min_hole_sec)
            artifact = TurnsArtifact(
                schema_version="1",
                job_id=resolved_job_id,
                diarizer="wespeaker_onnx",
                speaker_count=0,
                turns=[],
                holes=holes,
                merge=TurnMergeInfo(
                    same_speaker_gap_sec=cfg.merge_same_speaker_gap_sec,
                    absorb_shorter_than_sec=cfg.absorb_turn_shorter_than_sec,
                ),
                runtime_sec=round(time.time() - t0, 3),
            )
            dump_artifact(artifact, wav_path.parent / "turns.json")
            return artifact

        audio, sr = sf.read(str(wav_path))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)

        embedder = self._get_embedder()

        segments: list[tuple[float, float]] = []
        embeddings: list[np.ndarray] = []

        window_sec = 2.0
        step_sec = 1.0
        min_segment_sec = 0.5

        for region in speech.regions:
            dur = region.end - region.start
            if dur < min_segment_sec:
                continue

            r_start_idx = int(region.start * sr)
            r_end_idx = int(region.end * sr)

            if dur <= 3.0:
                slice_audio = audio[r_start_idx:r_end_idx]
                if len(slice_audio) > 0:
                    emb = embedder.embed(slice_audio)
                    segments.append((region.start, region.end))
                    embeddings.append(emb)
            else:
                win_len = int(window_sec * sr)
                step_len = int(step_sec * sr)
                curr = r_start_idx
                while curr + win_len <= r_end_idx:
                    emb = embedder.embed(audio[curr : curr + win_len])
                    s_time = round(curr / sr, 3)
                    e_time = round((curr + win_len) / sr, 3)
                    segments.append((s_time, e_time))
                    embeddings.append(emb)
                    curr += step_len

                if curr < r_end_idx and (r_end_idx - curr) >= int(min_segment_sec * sr):
                    emb = embedder.embed(audio[curr:r_end_idx])
                    segments.append((round(curr / sr, 3), round(r_end_idx / sr, 3)))
                    embeddings.append(emb)

        if not embeddings:
            holes = find_holes([], total_duration, cfg.min_hole_sec)
            artifact = TurnsArtifact(
                schema_version="1",
                job_id=resolved_job_id,
                diarizer="wespeaker_onnx",
                speaker_count=0,
                turns=[],
                holes=holes,
                merge=TurnMergeInfo(
                    same_speaker_gap_sec=cfg.merge_same_speaker_gap_sec,
                    absorb_shorter_than_sec=cfg.absorb_turn_shorter_than_sec,
                ),
                runtime_sec=round(time.time() - t0, 3),
            )
            dump_artifact(artifact, wav_path.parent / "turns.json")
            return artifact

        X = np.stack(embeddings)
        if len(X) == 1:
            labels = [0]
        else:
            clusterer = AgglomerativeClustering(
                metric="cosine",
                linkage="average",
                distance_threshold=0.5,
                n_clusters=None,
            )
            labels = clusterer.fit_predict(X).tolist()

        raw_turns: list[dict[str, Any]] = []
        for (s, e), lbl in zip(segments, labels, strict=True):
            raw_turns.append(
                {
                    "start": s,
                    "end": e,
                    "speaker": f"SPEAKER_{lbl:02d}",
                }
            )

        # Выполняем слияние по контракту
        merged = merge_turns(
            raw_turns,
            same_speaker_gap_sec=cfg.merge_same_speaker_gap_sec,
            absorb_shorter_than_sec=cfg.absorb_turn_shorter_than_sec,
        )

        # Устраняем взаимное перекрытие соседних реплик разных дикторов если возникло
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

        holes = find_holes(merged, total_duration, min_hole_sec=cfg.min_hole_sec)
        unique_speakers = len(set(t.speaker for t in merged))

        artifact = TurnsArtifact(
            schema_version="1",
            job_id=resolved_job_id,
            diarizer="wespeaker_onnx",
            speaker_count=unique_speakers,
            turns=merged,
            holes=holes,
            merge=TurnMergeInfo(
                same_speaker_gap_sec=cfg.merge_same_speaker_gap_sec,
                absorb_shorter_than_sec=cfg.absorb_turn_shorter_than_sec,
            ),
            runtime_sec=round(time.time() - t0, 3),
        )

        dump_artifact(artifact, wav_path.parent / "turns.json")
        return artifact

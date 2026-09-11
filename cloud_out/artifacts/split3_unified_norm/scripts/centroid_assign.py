"""Thin WeSpeaker helper: part1 AHC centroids, later parts nearest-centroid assign.

Does not modify product diarizer sources. Reuses windowing/merge/AHC parameters
from ``WeSpeakerDiarizer`` and ``config`` (distance threshold 0.85).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import soundfile as sf
from sklearn.cluster import AgglomerativeClustering

from transcriber.asr.holes import find_holes
from transcriber.config.schema import DiarizationConfig
from transcriber.diarization.merge import merge_turns
from transcriber.diarization.regions import Interval, merge_speech_regions
from transcriber.diarization.wespeaker import WeSpeakerDiarizer, _l2_normalize, _renumber_speakers
from transcriber.models.artifacts import (
    SpeechArtifact,
    TurnItem,
    TurnMergeInfo,
    TurnsArtifact,
    dump_artifact,
)


def cosine_distance_matrix(points: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """Pairwise cosine distance for L2-normalized rows: 1 - dot."""
    dots = np.clip(points @ centroids.T, -1.0, 1.0)
    return 1.0 - dots


def _ahc_labels(x: np.ndarray, distance_threshold: float) -> list[int]:
    if len(x) == 1:
        return [0]
    clusterer = AgglomerativeClustering(
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
        n_clusters=None,
    )
    return clusterer.fit_predict(x).tolist()


def extract_wespeaker_windows(
    wav_path: Any,
    speech: SpeechArtifact,
    cfg: DiarizationConfig,
    embedder: Any,
) -> tuple[list[tuple[float, float]], np.ndarray]:
    """Same windowing as product WeSpeakerDiarizer.diarize (not a rewrite of clustering)."""
    audio, sr = sf.read(str(wav_path))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)

    vad_intervals = [Interval(start=r.start, end=r.end) for r in speech.regions]
    speech_islands = merge_speech_regions(
        vad_intervals,
        max_gap_sec=cfg.merge.vad_premerge_gap_sec,
        min_duration_sec=cfg.embed.min_sec,
    )

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
        return [], np.zeros((0, 0), dtype=np.float64)
    x = _l2_normalize(np.stack(embeddings))
    return segments, x


def _clip_overlaps(merged: list[TurnItem]) -> list[TurnItem]:
    out = list(merged)
    for i in range(len(out) - 1):
        if out[i].end > out[i + 1].start:
            new_boundary = round(out[i + 1].start, 3)
            if new_boundary > out[i].start:
                out[i] = TurnItem(
                    id=out[i].id,
                    start=out[i].start,
                    end=new_boundary,
                    speaker=out[i].speaker,
                )
    return out


def _turns_from_window_speakers(
    segments: list[tuple[float, float]],
    speaker_ids: list[str],
    cfg: DiarizationConfig,
    *,
    job_id: str,
    total_duration: float,
    runtime_sec: float,
    compact_renumber: bool,
) -> TurnsArtifact:
    raw_turns: list[dict[str, Any]] = []
    for (start, end), spk in zip(segments, speaker_ids, strict=True):
        raw_turns.append({"start": start, "end": end, "speaker": spk})
    merged = merge_turns(
        raw_turns,
        same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
        absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
    )
    merged = _clip_overlaps(merged)
    if compact_renumber:
        merged = _renumber_speakers(merged)
    holes = find_holes(merged, total_duration, min_hole_sec=cfg.merge.min_hole_sec)
    unique_speakers = len({t.speaker for t in merged})
    return TurnsArtifact(
        schema_version="1",
        job_id=job_id,
        diarizer="wespeaker_onnx",
        speaker_count=unique_speakers,
        turns=merged,
        holes=holes,
        merge=TurnMergeInfo(
            same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
            absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
        ),
        runtime_sec=runtime_sec,
    )


@dataclass
class SpeakerGallery:
    """Stable SPEAKER_* ids with L2-normalized cosine centroids."""

    threshold: float
    speakers: list[dict[str, Any]] = field(default_factory=list)

    def _matrix(self) -> np.ndarray:
        if not self.speakers:
            return np.zeros((0, 0), dtype=np.float64)
        return np.stack([np.asarray(s["centroid"], dtype=np.float64) for s in self.speakers])

    def _next_id(self) -> str:
        used = {int(s["id"].split("_")[1]) for s in self.speakers}
        idx = 0
        while idx in used:
            idx += 1
        return f"SPEAKER_{idx:02d}"

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": "1",
            "distance_metric": "cosine",
            "cluster_distance_threshold": self.threshold,
            "speakers": [
                {
                    "id": s["id"],
                    "n_windows": int(s["n_windows"]),
                    "centroid": [round(float(x), 6) for x in s["centroid"]],
                }
                for s in self.speakers
            ],
            "id_map": {s["id"]: s["id"] for s in self.speakers},
        }

    @classmethod
    def from_ahc(
        cls,
        embeddings: np.ndarray,
        raw_labels: list[int],
        final_ids: list[str],
        threshold: float,
    ) -> SpeakerGallery:
        gallery = cls(threshold=threshold)
        by_spk: dict[str, list[np.ndarray]] = {}
        for vec, spk in zip(embeddings, final_ids, strict=True):
            by_spk.setdefault(spk, []).append(vec)
        # Keep first-appearance order of final_ids
        order: list[str] = []
        for spk in final_ids:
            if spk not in order:
                order.append(spk)
        for spk in order:
            stacked = _l2_normalize(np.stack(by_spk[spk]))
            mean = _l2_normalize(stacked.mean(axis=0, keepdims=True))[0]
            gallery.speakers.append(
                {
                    "id": spk,
                    "n_windows": int(len(by_spk[spk])),
                    "centroid": mean.astype(np.float64),
                }
            )
        return gallery

    def assign(self, embeddings: np.ndarray) -> tuple[list[str], dict[str, Any]]:
        """Assign rows to existing centroids or AHC leftover windows into new ids."""
        n = len(embeddings)
        assigned = [""] * n
        min_dist = [None] * n
        matched_idx: list[int] = []
        unmatched_idx: list[int] = []
        log_windows: list[dict[str, Any]] = []

        if n == 0:
            return [], {"windows": [], "matched": 0, "new": 0, "new_speaker_ids": []}

        if self.speakers:
            cents = self._matrix()
            dist = cosine_distance_matrix(embeddings, cents)
            best = dist.min(axis=1)
            best_j = dist.argmin(axis=1)
            for i in range(n):
                d = float(best[i])
                min_dist[i] = d
                if d <= self.threshold:
                    assigned[i] = str(self.speakers[int(best_j[i])]["id"])
                    matched_idx.append(i)
                else:
                    unmatched_idx.append(i)
        else:
            unmatched_idx = list(range(n))

        new_ids: list[str] = []
        leftover_label_to_id: dict[int, str] = {}
        if unmatched_idx:
            leftover = embeddings[np.array(unmatched_idx)]
            leftover_labels = _ahc_labels(leftover, self.threshold)
            first_vec: dict[int, np.ndarray] = {}
            for vec, lab in zip(leftover, leftover_labels, strict=True):
                first_vec.setdefault(int(lab), vec)
            for lab, vec in first_vec.items():
                leftover_label_to_id[lab] = self._next_id()
                self.speakers.append(
                    {
                        "id": leftover_label_to_id[lab],
                        "n_windows": 0,
                        "centroid": vec.astype(np.float64),
                    }
                )
                new_ids.append(leftover_label_to_id[lab])
            for local_i, lab in zip(unmatched_idx, leftover_labels, strict=True):
                assigned[local_i] = leftover_label_to_id[int(lab)]

        # Recompute centroids for speakers that received windows this part
        by_spk: dict[str, list[int]] = {}
        for i, spk in enumerate(assigned):
            by_spk.setdefault(spk, []).append(i)
        for spk, idxs in by_spk.items():
            mean = _l2_normalize(embeddings[np.array(idxs)].mean(axis=0, keepdims=True))[0]
            slot = next(s for s in self.speakers if s["id"] == spk)
            old_n = int(slot["n_windows"])
            new_n = len(idxs)
            if old_n <= 0:
                slot["centroid"] = mean.astype(np.float64)
                slot["n_windows"] = new_n
            else:
                blended = _l2_normalize(
                    (
                        np.asarray(slot["centroid"], dtype=np.float64) * old_n + mean * new_n
                    ).reshape(1, -1)
                )[0]
                slot["centroid"] = blended.astype(np.float64)
                slot["n_windows"] = old_n + new_n

        for i in range(n):
            log_windows.append(
                {
                    "index": i,
                    "assigned": assigned[i],
                    "min_distance": None if min_dist[i] is None else round(float(min_dist[i]), 4),
                    "new_speaker": i in unmatched_idx,
                }
            )
        summary = {
            "matched": len(matched_idx),
            "new": len(unmatched_idx),
            "new_speaker_ids": new_ids,
            "speakers_after": [s["id"] for s in self.speakers],
            "windows": log_windows,
        }
        return assigned, summary


def window_speakers_after_turns(
    segments: list[tuple[float, float]],
    raw_speaker_ids: list[str],
    turns: list[TurnItem],
) -> list[str]:
    """Map each window to the overlapping merged turn speaker (post-absorb)."""
    out: list[str] = []
    for (start, end), raw in zip(segments, raw_speaker_ids, strict=True):
        mid = (start + end) / 2.0
        hit = None
        for turn in turns:
            if turn.start - 1e-6 <= mid <= turn.end + 1e-6:
                hit = turn.speaker
                break
        out.append(hit or raw)
    return out


def diarize_part(
    wav_path: Any,
    speech: SpeechArtifact,
    cfg: DiarizationConfig,
    *,
    job_id: str,
    gallery: SpeakerGallery | None,
    mode: str,
) -> tuple[TurnsArtifact, SpeakerGallery, dict[str, Any]]:
    """Part1: AHC + save gallery. Part2/3: assign to gallery, else new ids."""
    import time
    from pathlib import Path

    t0 = time.time()
    wav = Path(wav_path)
    info = sf.info(str(wav))
    total_duration = round(float(info.duration), 3)
    embedder = WeSpeakerDiarizer()._get_embedder()
    segments, embeddings = extract_wespeaker_windows(wav, speech, cfg, embedder)
    threshold = float(cfg.embed.cluster_distance_threshold)
    assign_log: dict[str, Any] = {
        "mode": mode,
        "n_windows": len(segments),
        "threshold": threshold,
    }

    if not segments:
        gallery = gallery or SpeakerGallery(threshold=threshold)
        artifact = TurnsArtifact(
            schema_version="1",
            job_id=job_id,
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
        dump_artifact(artifact, wav.parent / "turns.json")
        return artifact, gallery, assign_log

    if mode == "ahc":
        raw_labels = _ahc_labels(embeddings, threshold)
        raw_ids = [f"SPEAKER_{int(lbl):02d}" for lbl in raw_labels]
        artifact = _turns_from_window_speakers(
            segments,
            raw_ids,
            cfg,
            job_id=job_id,
            total_duration=total_duration,
            runtime_sec=round(time.time() - t0, 3),
            compact_renumber=True,
        )
        final_for_windows = window_speakers_after_turns(segments, raw_ids, artifact.turns)
        gallery = SpeakerGallery.from_ahc(embeddings, raw_labels, final_for_windows, threshold)
        assign_log["matched"] = len(segments)
        assign_log["new"] = 0
        assign_log["speakers"] = [s["id"] for s in gallery.speakers]
        assign_log["raw_label_to_final"] = {
            f"SPEAKER_{int(lbl):02d}": fin
            for lbl, fin in zip(raw_labels, final_for_windows, strict=True)
        }
    else:
        if gallery is None:
            raise RuntimeError("centroid assign requires a gallery from part1")
        speaker_ids, summary = gallery.assign(embeddings)
        assign_log.update({k: v for k, v in summary.items() if k != "windows"})
        assign_log["windows"] = summary["windows"]
        # attach window times for debugging (not embeddings)
        for row, (start, end) in zip(assign_log["windows"], segments, strict=True):
            row["start"] = start
            row["end"] = end
        artifact = _turns_from_window_speakers(
            segments,
            speaker_ids,
            cfg,
            job_id=job_id,
            total_duration=total_duration,
            runtime_sec=round(time.time() - t0, 3),
            compact_renumber=False,
        )
        artifact = artifact.model_copy(
            update={"runtime_sec": round(time.time() - t0, 3)}
        )

    dump_artifact(artifact, wav.parent / "turns.json")
    return artifact, gallery, assign_log

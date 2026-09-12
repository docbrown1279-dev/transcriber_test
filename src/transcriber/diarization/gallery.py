"""Speaker gallery + method-B nearest-centroid assign (product TTFT mid-diarization).

Ported from research centroid_assign.py; lives under src/ (no cloud_out imports).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
from sklearn.cluster import AgglomerativeClustering

from transcriber.diarization.wespeaker import l2_normalize


def cosine_distance_matrix(points: np.ndarray, centroids: np.ndarray) -> np.ndarray:
    """Pairwise cosine distance for L2-normalized rows: 1 - dot."""
    dots = np.clip(points @ centroids.T, -1.0, 1.0)
    return 1.0 - dots


def ahc_labels(x: np.ndarray, distance_threshold: float) -> list[int]:
    if len(x) == 0:
        return []
    if len(x) == 1:
        return [0]
    clusterer = AgglomerativeClustering(
        metric="cosine",
        linkage="average",
        distance_threshold=distance_threshold,
        n_clusters=None,
    )
    return clusterer.fit_predict(x).tolist()


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
        }

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> SpeakerGallery:
        gallery = cls(threshold=float(data["cluster_distance_threshold"]))
        for row in data.get("speakers", []):
            gallery.speakers.append(
                {
                    "id": str(row["id"]),
                    "n_windows": int(row["n_windows"]),
                    "centroid": np.asarray(row["centroid"], dtype=np.float64),
                }
            )
        return gallery

    @classmethod
    def from_ahc(
        cls,
        embeddings: np.ndarray,
        final_ids: list[str],
        threshold: float,
    ) -> SpeakerGallery:
        gallery = cls(threshold=threshold)
        by_spk: dict[str, list[np.ndarray]] = {}
        for vec, spk in zip(embeddings, final_ids, strict=True):
            by_spk.setdefault(spk, []).append(vec)
        order: list[str] = []
        for spk in final_ids:
            if spk not in order:
                order.append(spk)
        for spk in order:
            stacked = l2_normalize(np.stack(by_spk[spk]))
            mean = l2_normalize(stacked.mean(axis=0, keepdims=True))[0]
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
        min_dist: list[float | None] = [None] * n
        matched_idx: list[int] = []
        unmatched_idx: list[int] = []

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
            leftover_labels = ahc_labels(leftover, self.threshold)
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

        by_spk: dict[str, list[int]] = {}
        for i, spk in enumerate(assigned):
            by_spk.setdefault(spk, []).append(i)
        for spk, idxs in by_spk.items():
            mean = l2_normalize(embeddings[np.array(idxs)].mean(axis=0, keepdims=True))[0]
            slot = next(s for s in self.speakers if s["id"] == spk)
            old_n = int(slot["n_windows"])
            new_n = len(idxs)
            if old_n <= 0:
                slot["centroid"] = mean.astype(np.float64)
                slot["n_windows"] = new_n
            else:
                blended = l2_normalize(
                    (
                        np.asarray(slot["centroid"], dtype=np.float64) * old_n + mean * new_n
                    ).reshape(1, -1)
                )[0]
                slot["centroid"] = blended.astype(np.float64)
                slot["n_windows"] = old_n + new_n

        log_windows = [
            {
                "index": i,
                "assigned": assigned[i],
                "min_distance": None if min_dist[i] is None else round(float(min_dist[i]), 4),
                "new_speaker": i in unmatched_idx,
            }
            for i in range(n)
        ]
        summary = {
            "matched": len(matched_idx),
            "new": len(unmatched_idx),
            "new_speaker_ids": new_ids,
            "speakers_after": [s["id"] for s in self.speakers],
            "windows": log_windows,
        }
        return assigned, summary

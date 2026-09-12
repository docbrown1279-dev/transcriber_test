"""EOS V1: AHC on saved window embeddings + greedy duration-overlap remap."""

from __future__ import annotations

from typing import Any

import numpy as np

from transcriber.diarization.gallery import ahc_labels


def greedy_remap_by_duration(
    cluster_labels: list[int],
    published_ids: list[str],
    durations: list[float],
    *,
    published_order: list[str] | None = None,
) -> dict[int, str]:
    """Map AHC cluster labels → SPEAKER_* by greedy duration overlap.

    ``published_ids[i]`` is the mid-run speaker for window i.
    Unmapped clusters receive new compact SPEAKER_* ids after used ones.
    """
    if len(cluster_labels) != len(published_ids) or len(cluster_labels) != len(durations):
        raise ValueError("cluster_labels, published_ids, durations must have equal length")
    if not cluster_labels:
        return {}

    clusters = sorted(set(cluster_labels))
    pubs = list(dict.fromkeys(published_ids))
    if published_order:
        pubs = list(dict.fromkeys([*published_order, *pubs]))

    overlap: dict[tuple[int, str], float] = {}
    for lab, pub, dur in zip(cluster_labels, published_ids, durations, strict=True):
        key = (int(lab), pub)
        overlap[key] = overlap.get(key, 0.0) + float(dur)

    remaining_c = set(clusters)
    remaining_p = set(pubs)
    mapping: dict[int, str] = {}

    while remaining_c and remaining_p:
        best_pair: tuple[int, str] | None = None
        best_val = -1.0
        for c in remaining_c:
            for p in remaining_p:
                val = overlap.get((c, p), 0.0)
                if val > best_val:
                    best_val = val
                    best_pair = (c, p)
        if best_pair is None or best_val <= 0.0:
            break
        c, p = best_pair
        mapping[c] = p
        remaining_c.remove(c)
        remaining_p.remove(p)

    used = {int(s.split("_")[1]) for s in mapping.values() if s.startswith("SPEAKER_")}
    for pub in pubs:
        if pub.startswith("SPEAKER_"):
            used.add(int(pub.split("_")[1]))

    def _next_id() -> str:
        idx = 0
        while idx in used:
            idx += 1
        used.add(idx)
        return f"SPEAKER_{idx:02d}"

    for c in sorted(remaining_c):
        mapping[c] = _next_id()

    return mapping


def refine_window_speakers_v1(
    embeddings: np.ndarray,
    segments: list[tuple[float, float]],
    mid_speakers: list[str],
    *,
    distance_threshold: float,
    published_order: list[str] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """AHC all windows → greedy remap to mid-run SPEAKER_* ids.

    Returns final speaker id per window and a small debug summary.
    """
    n = len(segments)
    if n == 0:
        return [], {"n_windows": 0, "n_clusters": 0, "mapping": {}}
    if len(embeddings) != n or len(mid_speakers) != n:
        raise ValueError("embeddings, segments, mid_speakers length mismatch")

    labels = ahc_labels(embeddings, distance_threshold)
    durations = [max(0.0, end - start) for start, end in segments]
    mapping = greedy_remap_by_duration(
        labels,
        mid_speakers,
        durations,
        published_order=published_order,
    )
    final = [mapping[int(lab)] for lab in labels]
    summary = {
        "n_windows": n,
        "n_clusters": len(set(labels)),
        "mapping": {str(k): v for k, v in sorted(mapping.items())},
        "final_speakers": sorted(set(final)),
    }
    return final, summary

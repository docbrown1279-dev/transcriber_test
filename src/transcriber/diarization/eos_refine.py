"""EOS V1: AHC on saved window embeddings + greedy duration-overlap remap."""

from __future__ import annotations

from typing import Any

import numpy as np

from transcriber.diarization.gallery import ahc_labels, cosine_distance_matrix
from transcriber.diarization.wespeaker import l2_normalize


def union_speech_sec(intervals: list[tuple[float, float]]) -> float:
    """Merged coverage of overlapping windows (not a raw duration sum)."""
    if not intervals:
        return 0.0
    ordered = sorted((float(s), float(e)) for s, e in intervals)
    total = 0.0
    cur_s, cur_e = ordered[0]
    for start, end in ordered[1:]:
        if start <= cur_e:
            cur_e = max(cur_e, end)
        else:
            total += cur_e - cur_s
            cur_s, cur_e = start, end
    total += cur_e - cur_s
    return float(total)


def centroids_from_windows(
    embeddings: np.ndarray,
    speakers: list[str],
) -> dict[str, np.ndarray]:
    """L2 mean embedding per speaker id (skip empty)."""
    by: dict[str, list[int]] = {}
    for i, spk in enumerate(speakers):
        by.setdefault(spk, []).append(i)
    out: dict[str, np.ndarray] = {}
    for spk, idxs in by.items():
        stacked = embeddings[np.array(idxs, dtype=int)]
        out[spk] = l2_normalize(stacked.mean(axis=0, keepdims=True))[0]
    return out


def absorb_micro_speaker_map(
    speech_sec: dict[str, float],
    centroids: dict[str, np.ndarray],
    *,
    min_speech_sec: float,
) -> tuple[dict[str, str], dict[str, Any]]:
    """Build SPEAKER_* remap using UI speech totals (sum of segment lengths).

    Ids with speech < ``min_speech_sec`` map to the nearest centroid among remaining
    ids. Returns a full map (identity for kept ids) and a debug summary.
    """
    if min_speech_sec <= 0 or not speech_sec:
        identity = {spk: spk for spk in speech_sec}
        return identity, {
            "absorbed": [],
            "disabled": min_speech_sec <= 0,
            "metric": "ui_speech_sum",
        }

    remaining = dict(speech_sec)
    remap: dict[str, str] = {spk: spk for spk in remaining}
    absorbed: list[dict[str, Any]] = []

    for _ in range(max(1, len(remaining))):
        if len(remaining) <= 1:
            break
        micros = sorted(
            ((dur, spk) for spk, dur in remaining.items() if dur < min_speech_sec),
            key=lambda item: item[0],
        )
        if not micros:
            break
        _, micro = micros[0]
        others = [spk for spk in remaining if spk != micro and spk in centroids]
        if micro not in centroids or not others:
            # Cannot place — drop from candidates to avoid infinite loop.
            remaining.pop(micro, None)
            continue
        micro_c = centroids[micro].reshape(1, -1)
        other_c = np.stack([centroids[spk] for spk in others])
        dist = cosine_distance_matrix(micro_c, other_c)[0]
        target = others[int(np.argmin(dist))]
        d_best = float(dist.min())
        # Point every id currently mapping to micro → target.
        for src, dst in list(remap.items()):
            if dst == micro:
                remap[src] = target
        remaining[target] = remaining.get(target, 0.0) + remaining.pop(micro)
        absorbed.append(
            {
                "from": micro,
                "to": target,
                "speech_sec": round(float(speech_sec.get(micro, 0.0)), 3),
                "distance": round(d_best, 4),
            }
        )

    return remap, {
        "absorbed": absorbed,
        "min_speaker_speech_sec": min_speech_sec,
        "final_speakers": sorted(set(remap.values())),
        "metric": "ui_speech_sum",
        "speech_before": {k: round(float(v), 3) for k, v in sorted(speech_sec.items())},
    }


def apply_speaker_id_map(speakers: list[str], remap: dict[str, str]) -> list[str]:
    return [remap.get(spk, spk) for spk in speakers]


def absorb_micro_speakers(
    embeddings: np.ndarray,
    segments: list[tuple[float, float]],
    speakers: list[str],
    *,
    min_speech_sec: float,
    speech_sec: dict[str, float] | None = None,
) -> tuple[list[str], dict[str, Any]]:
    """Convenience: absorb using optional UI ``speech_sec``, else window-union."""
    n = len(speakers)
    if n == 0 or min_speech_sec <= 0:
        return list(speakers), {
            "absorbed": [],
            "disabled": min_speech_sec <= 0,
            "metric": "ui_speech_sum" if speech_sec is not None else "window_union",
        }
    if len(embeddings) != n or len(segments) != n:
        raise ValueError("embeddings, segments, speakers length mismatch")

    cents = centroids_from_windows(embeddings, speakers)
    if speech_sec is None:
        by_iv: dict[str, list[tuple[float, float]]] = {}
        for spk, seg in zip(speakers, segments, strict=True):
            by_iv.setdefault(spk, []).append(seg)
        speech_sec = {spk: union_speech_sec(ivs) for spk, ivs in by_iv.items()}
        metric_note = "window_union"
    else:
        metric_note = "ui_speech_sum"

    remap, summary = absorb_micro_speaker_map(
        speech_sec, cents, min_speech_sec=min_speech_sec
    )
    summary["metric"] = metric_note
    return apply_speaker_id_map(speakers, remap), summary


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
    """AHC all windows → greedy remap. Micro-absorb is applied later (UI speech)."""
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
        "micro_absorb": {"deferred": True, "metric": "ui_speech_sum"},
    }
    return final, summary

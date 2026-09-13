"""H1 / H2 / H3 cluster-rebuild hypotheses. Separate runs; no sticky-previous-window."""

from __future__ import annotations

from typing import Any

import numpy as np

from centroid_assign import (
    SpeakerGallery,
    _ahc_labels,
    _turns_from_window_speakers,
    cosine_distance_matrix,
)
from transcriber.config.schema import DiarizationConfig
from transcriber.diarization.wespeaker import _l2_normalize
from transcriber.models.artifacts import TurnsArtifact

# Prompt constants (not product config). Do not combine hypotheses.
CLEAR_WINNER_MARGIN = 0.05
MICRO_CLUSTER_SPEECH_SEC = 2.0
HOTSPOT_ABS = (365.0, 375.5)
SHORT_1S = 1.0
SHORT_2S = 2.0


def _round3(value: float) -> float:
    return round(float(value), 3)


def _write_json(path: Any, payload: dict[str, Any]) -> None:
    import json
    from pathlib import Path

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


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
    return _round3(total)


def _cluster_mean(embeddings: np.ndarray, idxs: list[int]) -> np.ndarray:
    stacked = embeddings[np.array(idxs, dtype=int)]
    return _l2_normalize(stacked.mean(axis=0, keepdims=True))[0]


def _appearance_clusters(labels: list[int]) -> list[int]:
    order: list[int] = []
    for lab in labels:
        lab_i = int(lab)
        if lab_i not in order:
            order.append(lab_i)
    return order


def _gallery_distances(
    mean: np.ndarray, gallery: SpeakerGallery
) -> tuple[str | None, float | None, float | None]:
    if not gallery.speakers:
        return None, None, None
    dist = cosine_distance_matrix(mean.reshape(1, -1), gallery._matrix())[0]
    order = np.argsort(dist)
    best_id = str(gallery.speakers[int(order[0])]["id"])
    d_best = float(dist[int(order[0])])
    d_second = float(dist[int(order[1])]) if len(order) > 1 else None
    return best_id, d_best, d_second


def _append_new_speaker(gallery: SpeakerGallery, centroid: np.ndarray) -> str:
    new_id = gallery._next_id()
    gallery.speakers.append(
        {
            "id": new_id,
            "n_windows": 0,
            "centroid": np.asarray(centroid, dtype=np.float64),
        }
    )
    return new_id


def h1_cluster_then_match(
    gallery: SpeakerGallery,
    embeddings: np.ndarray,
    segments: list[tuple[float, float]],
) -> tuple[list[str], dict[str, Any]]:
    """Local AHC on the part, then whole-cluster match to a snapshot of the gallery."""
    n = len(embeddings)
    if n == 0:
        return [], {"mode": "H1_cluster_then_match", "clusters": [], "new_speaker_ids": []}

    labels = _ahc_labels(embeddings, gallery.threshold)
    snapshot = gallery.clone()
    assigned = [""] * n
    cluster_log: list[dict[str, Any]] = []
    new_ids: list[str] = []

    by_lab: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        by_lab.setdefault(int(lab), []).append(i)

    for lab in _appearance_clusters(labels):
        idxs = by_lab[lab]
        mean = _cluster_mean(embeddings, idxs)
        speech_sec = union_speech_sec([segments[i] for i in idxs])
        best_id, d_best, d_second = _gallery_distances(mean, snapshot)
        if d_best is not None and d_best <= gallery.threshold and best_id is not None:
            chosen = best_id
            decision = "gallery_match"
        else:
            chosen = _append_new_speaker(gallery, mean)
            new_ids.append(chosen)
            decision = "new_cluster_id"
        for i in idxs:
            assigned[i] = chosen
        cluster_log.append(
            {
                "local_label": lab,
                "n_windows": len(idxs),
                "speech_union_sec": speech_sec,
                "d_best": None if d_best is None else round(d_best, 4),
                "d_second": None if d_second is None else round(d_second, 4),
                "nearest_gallery_id": best_id,
                "assigned_id": chosen,
                "decision": decision,
                "window_indices": idxs,
            }
        )

    gallery.blend_assignments(embeddings, assigned)
    return assigned, {
        "mode": "H1_cluster_then_match",
        "n_windows": n,
        "n_local_clusters": len(cluster_log),
        "new_speaker_ids": new_ids,
        "speakers_after": [s["id"] for s in gallery.speakers],
        "clusters": cluster_log,
    }


def h2_refine_reassign(
    gallery: SpeakerGallery,
    embeddings: np.ndarray,
    segments: list[tuple[float, float]],
) -> tuple[list[str], dict[str, Any]]:
    """Baseline window assign, refine centroids, re-assign once (leftover AHC on pass 2)."""
    del segments  # window times live in the caller log
    n = len(embeddings)
    if n == 0:
        return [], {"mode": "H2_refine_reassign", "new_speaker_ids": []}

    prior = gallery.clone()
    assigned1, pass1 = prior.match_existing(embeddings)

    refreshed = prior.clone()
    refreshed.refresh_centroids_keep_counts(embeddings, assigned1)

    assigned2, pass2_match = refreshed.match_existing(embeddings)
    leftover = refreshed.leftover_ahc(embeddings, assigned2)

    # Commit: restore prior centroid/n for original ids, keep leftover new ids, blend pass-2 labels.
    new_slots = [
        {
            "id": slot["id"],
            "n_windows": 0,
            "centroid": np.asarray(slot["centroid"], dtype=np.float64).copy(),
        }
        for slot in refreshed.speakers
        if slot["id"] not in {s["id"] for s in prior.speakers}
    ]
    gallery.speakers = []
    for slot in prior.speakers:
        gallery.speakers.append(
            {
                "id": slot["id"],
                "n_windows": int(slot["n_windows"]),
                "centroid": np.asarray(slot["centroid"], dtype=np.float64).copy(),
            }
        )
    gallery.speakers.extend(new_slots)
    gallery.blend_assignments(embeddings, assigned2)

    flipped = sum(
        1 for a, b in zip(assigned1, assigned2, strict=True) if (a or "") != (b or "")
    )
    return assigned2, {
        "mode": "H2_refine_reassign",
        "n_windows": n,
        "pass1_matched": pass1["matched"],
        "pass1_unmatched": pass1["unmatched"],
        "pass2_matched_existing": pass2_match["matched"],
        "pass2_unmatched_before_leftover": pass2_match["unmatched"],
        "new_speaker_ids": leftover["new_speaker_ids"],
        "windows_relabeled_pass1_to_pass2": flipped,
        "speakers_after": [s["id"] for s in gallery.speakers],
        "pass1_windows": pass1["windows"],
        "pass2_windows": [
            {
                **row,
                "assigned_final": assigned2[row["index"]],
            }
            for row in pass2_match["windows"]
        ],
        "leftover": {
            "new": leftover["new"],
            "new_speaker_ids": leftover["new_speaker_ids"],
            "unmatched_idx": leftover["unmatched_idx"],
        },
    }


def h3_cluster_clear_winner(
    gallery: SpeakerGallery,
    embeddings: np.ndarray,
    segments: list[tuple[float, float]],
) -> tuple[list[str], dict[str, Any]]:
    """H1 plus clear-winner margin; short ambiguous clusters map to nearest gallery id."""
    n = len(embeddings)
    if n == 0:
        return [], {"mode": "H3_cluster_clear_winner", "clusters": [], "new_speaker_ids": []}

    labels = _ahc_labels(embeddings, gallery.threshold)
    snapshot = gallery.clone()
    assigned = [""] * n
    cluster_log: list[dict[str, Any]] = []
    new_ids: list[str] = []
    only_one_gallery = len(snapshot.speakers) <= 1

    by_lab: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        by_lab.setdefault(int(lab), []).append(i)

    for lab in _appearance_clusters(labels):
        idxs = by_lab[lab]
        mean = _cluster_mean(embeddings, idxs)
        speech_sec = union_speech_sec([segments[i] for i in idxs])
        best_id, d_best, d_second = _gallery_distances(mean, snapshot)
        margin = None
        if d_best is not None and d_second is not None:
            margin = d_second - d_best
        clear = (
            d_best is not None
            and best_id is not None
            and d_best <= gallery.threshold
            and (only_one_gallery or (margin is not None and margin >= CLEAR_WINNER_MARGIN))
        )
        if clear and best_id is not None:
            chosen = best_id
            decision = "clear_winner"
        elif speech_sec >= MICRO_CLUSTER_SPEECH_SEC or best_id is None:
            chosen = _append_new_speaker(gallery, mean)
            new_ids.append(chosen)
            decision = "ambiguous_long_new_id" if best_id is not None else "no_gallery_new_id"
        else:
            chosen = best_id
            decision = "ambiguous_short_nearest"

        for i in idxs:
            assigned[i] = chosen
        cluster_log.append(
            {
                "local_label": lab,
                "n_windows": len(idxs),
                "speech_union_sec": speech_sec,
                "d_best": None if d_best is None else round(d_best, 4),
                "d_second": None if d_second is None else round(d_second, 4),
                "margin": None if margin is None else round(margin, 4),
                "clear_winner": clear,
                "nearest_gallery_id": best_id,
                "assigned_id": chosen,
                "decision": decision,
                "window_indices": idxs,
            }
        )

    gallery.blend_assignments(embeddings, assigned)
    return assigned, {
        "mode": "H3_cluster_clear_winner",
        "n_windows": n,
        "clear_winner_margin": CLEAR_WINNER_MARGIN,
        "micro_cluster_speech_sec": MICRO_CLUSTER_SPEECH_SEC,
        "n_local_clusters": len(cluster_log),
        "new_speaker_ids": new_ids,
        "speakers_after": [s["id"] for s in gallery.speakers],
        "clusters": cluster_log,
    }


def labels_to_turns(
    segments: list[tuple[float, float]],
    speaker_ids: list[str],
    cfg: DiarizationConfig,
    *,
    job_id: str,
    total_duration: float,
    runtime_sec: float,
) -> TurnsArtifact:
    return _turns_from_window_speakers(
        segments,
        speaker_ids,
        cfg,
        job_id=job_id,
        total_duration=total_duration,
        runtime_sec=runtime_sec,
        compact_renumber=False,
    )


def turns_metrics(
    *,
    hyp: str,
    part: str,
    turns: list[Any],
    part1_ids: list[str],
    abs_offset: float,
) -> dict[str, Any]:
    n_turns = len(turns)
    durs = [float(t.end) - float(t.start) for t in turns]
    speakers = [str(t.speaker) for t in turns]
    ids_sorted = sorted(set(speakers))
    switches = sum(1 for a, b in zip(speakers, speakers[1:], strict=False) if a != b)
    new_ids = sorted(set(ids_sorted) - set(part1_ids))
    hotspot: list[dict[str, Any]] = []
    if part == "part02":
        lo, hi = HOTSPOT_ABS
        for turn in turns:
            start_abs = _round3(float(turn.start) + abs_offset)
            end_abs = _round3(float(turn.end) + abs_offset)
            if end_abs > lo and start_abs < hi:
                hotspot.append(
                    {
                        "id": turn.id,
                        "start": _round3(float(turn.start)),
                        "end": _round3(float(turn.end)),
                        "start_abs": start_abs,
                        "end_abs": end_abs,
                        "speaker": str(turn.speaker),
                        "duration_sec": _round3(end_abs - start_abs),
                    }
                )
    return {
        "hyp": hyp,
        "part": part,
        "n_turns": n_turns,
        "n_turns_lt_1s": sum(1 for d in durs if d < SHORT_1S),
        "n_turns_lt_2s": sum(1 for d in durs if d < SHORT_2S),
        "n_speaker_switches": switches,
        "n_speakers": len(ids_sorted),
        "speaker_ids": ids_sorted,
        "new_ids_vs_part1": new_ids,
        "hotspot_365_375": hotspot,
    }

#!/usr/bin/env python3
"""Throwaway D5.diar-spectral research runner (not production pipeline).

Same WeSpeaker ResNet34 windows (1.5 / 0.75). Cluster the same embeddings with
AHC (M0), spectral+eigengap (M1), AHC→change-point spectral hybrid (M2), and
optional anchor→assign (M3). No crumb-primary, no K in [2,4] prior, no ASR/LLM,
no eval/gold, no src/ edits.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import soundfile as sf
import yaml
from sklearn.cluster import AgglomerativeClustering, KMeans

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

ONNX_THREADS = 2
os.environ.setdefault("OMP_NUM_THREADS", str(ONNX_THREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(ONNX_THREADS))
os.environ.setdefault("OPENBLAS_NUM_THREADS", str(ONNX_THREADS))
os.environ.setdefault("NUMEXPR_THREADS", str(ONNX_THREADS))
os.environ.setdefault("NUMEXPR_NUM_THREADS", str(ONNX_THREADS))
os.environ.setdefault("ORT_INTRA_OP_NUM_THREADS", str(ONNX_THREADS))

_ORT_SESSION = ort.InferenceSession


def _threaded_session(path: str, *args: Any, **kwargs: Any) -> ort.InferenceSession:
    if "sess_options" not in kwargs:
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = ONNX_THREADS
        opts.inter_op_num_threads = ONNX_THREADS
        kwargs["sess_options"] = opts
    return _ORT_SESSION(path, *args, **kwargs)


ort.InferenceSession = _threaded_session  # type: ignore[misc]

from speakeronnx import SpeakerEmbedder  # noqa: E402

from transcriber.config.loader import deep_merge  # noqa: E402
from transcriber.config.schema import DiarizationConfig, VadConfig  # noqa: E402
from transcriber.diarization.merge import merge_turns  # noqa: E402
from transcriber.diarization.regions import Interval, merge_speech_regions  # noqa: E402
from transcriber.diarization.wespeaker import _l2_normalize, _renumber_speakers  # noqa: E402
from transcriber.models.artifacts import TurnItem  # noqa: E402
from transcriber.vad.silero import SileroVadDetector  # noqa: E402

INPUTS = ROOT / "cloud_in" / "inputs"
OUT = ROOT / "cloud_out"
WORK = Path("/tmp/d5-diar-spectral")
TIMELINES = OUT / "timelines"

WINDOW_SEC = 1.5
STEP_SEC = 0.75
AHC_THRESHOLDS = (0.80, 0.85, 0.88)
K_CAP = 20
KNN_K = 10
HYBRID_NEIGHBORHOOD = 4
HYBRID_SEED_THRESHOLD = 0.85
COSINE_DIP_PERCENTILE = 20.0
ANCHOR_ASSIGN_MIN_COS = 0.0
GREETING_START = 42.0
GREETING_END = 45.0
CONCAT_SLICE_SEC = 60.0
CRUMB_LOG_SEC = 3.0
KMEANS_RANDOM_STATE = 0
KMEANS_N_INIT = 10
MIN_SPECTRAL_WINDOWS = 3

QUALITY_CLIPS: list[tuple[str, Path]] = [
    ("clip01", INPUTS / "clips" / "clip01.wav"),
    ("clip02", INPUTS / "clips" / "clip02.wav"),
    ("clip03", INPUTS / "clips" / "clip03.wav"),
    ("concat_01_02_03", INPUTS / "clips" / "concat_01_02_03.wav"),
    ("test_apartments", INPUTS / "regression" / "test_apartments.wav"),
    ("test_ninth", INPUTS / "regression" / "test_ninth.wav"),
]
TIMING_CLIP = ("timing_5min", INPUTS / "clips" / "timing_5min.wav")


class RssSampler:
    """Sample VmRSS of this process on a background thread."""

    def __init__(self, interval_sec: float = 0.2) -> None:
        self.interval_sec = interval_sec
        self.peak_kb = 0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="rss-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> int:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
        return self.peak_kb

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                text = Path("/proc/self/status").read_text(encoding="utf-8")
            except OSError:
                return
            for line in text.splitlines():
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    if len(parts) >= 2:
                        self.peak_kb = max(self.peak_kb, int(parts[1]))
                    break
            self._stop.wait(self.interval_sec)


def _round3(value: float) -> float:
    return round(float(value), 3)


def load_vad_diar_cfg() -> tuple[VadConfig, DiarizationConfig]:
    """Load vad + diarization from YAML without touching .env."""
    base = yaml.safe_load((ROOT / "config" / "base.yaml").read_text(encoding="utf-8"))
    demo = yaml.safe_load((ROOT / "config" / "profiles" / "demo.yaml").read_text(encoding="utf-8"))
    merged = deep_merge(base, demo)
    return (
        VadConfig.model_validate(merged["vad"]),
        DiarizationConfig.model_validate(merged["diarization"]),
    )


def speaker_speech(turns: list[TurnItem]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for turn in turns:
        out[turn.speaker] += turn.end - turn.start
    return {k: _round3(v) for k, v in sorted(out.items())}


def window_embeddings(
    audio: np.ndarray,
    sr: int,
    speech_islands: list[Interval],
    embedder: SpeakerEmbedder,
    window_sec: float,
    step_sec: float,
    min_embed: float,
) -> tuple[list[tuple[float, float]], np.ndarray, float]:
    """Same windowing as WeSpeakerDiarizer.diarize; returns segments, X, embed_wall."""
    segments: list[tuple[float, float]] = []
    embeddings: list[np.ndarray] = []
    t0 = time.perf_counter()
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
    embed_wall = time.perf_counter() - t0
    if not embeddings:
        empty = np.zeros((0, 1), dtype=np.float64)
        return segments, empty, embed_wall
    x = _l2_normalize(np.stack(embeddings))
    return segments, x, embed_wall


def cosine_knn_affinity(x: np.ndarray, knn_k: int = KNN_K) -> np.ndarray:
    """Symmetric k-NN graph on non-negative cosine similarity (not a speaker-count prior)."""
    n = len(x)
    if n == 0:
        return np.zeros((0, 0), dtype=np.float64)
    sim = np.clip(x @ x.T, 0.0, None)
    np.fill_diagonal(sim, 0.0)
    k = min(int(knn_k), n - 1)
    if k <= 0:
        return sim
    knn = np.zeros_like(sim)
    for i in range(n):
        idx = np.argpartition(sim[i], -k)[-k:]
        knn[i, idx] = sim[i, idx]
    return np.maximum(knn, knn.T)


def eigengap_k(lap_evals: np.ndarray, k_cap: int) -> tuple[int, list[float]]:
    """Largest gap among λ_1-λ_0 … λ_{k_cap}-λ_{k_cap-1}. K=1 is allowed (no 2–4 prior)."""
    n = int(lap_evals.size)
    if n <= 1:
        return 1, []
    cap = min(int(k_cap), n - 1)
    if cap < 1:
        return 1, []
    gaps = np.diff(lap_evals[: cap + 1])
    k = int(np.argmax(gaps) + 1)
    return k, [_round3(float(g)) for g in gaps]


def spectral_eigengap(
    x: np.ndarray,
    k_cap: int = K_CAP,
    knn_k: int = KNN_K,
) -> tuple[list[int], dict[str, Any], float]:
    """Ng–Jordan–Weiss spectral clustering; K from Laplacian eigengap, cap K_CAP."""
    t0 = time.perf_counter()
    n = len(x)
    if n == 0:
        return [], {"k": 0, "n_windows": 0, "eigengap_gaps": [], "lap_evals_head": []}, 0.0
    if n == 1:
        wall = time.perf_counter() - t0
        return [0], {"k": 1, "n_windows": 1, "eigengap_gaps": [], "lap_evals_head": [0.0]}, wall

    affinity = cosine_knn_affinity(x, knn_k=knn_k)
    degree = affinity.sum(axis=1)
    degree = np.maximum(degree, 1e-12)
    inv_sqrt = 1.0 / np.sqrt(degree)
    norm_aff = affinity * inv_sqrt[:, None] * inv_sqrt[None, :]
    norm_aff = 0.5 * (norm_aff + norm_aff.T)
    evals_s, evecs_s = np.linalg.eigh(norm_aff)
    # L_sym = I - D^{-1/2} A D^{-1/2}; eigenvalues 1 - λ_S (S evals ascending).
    lap_evals = np.sort(1.0 - evals_s[::-1])
    cap = min(int(k_cap), n - 1)
    k, gaps = eigengap_k(lap_evals, cap)
    meta: dict[str, Any] = {
        "k": int(k),
        "n_windows": int(n),
        "k_cap": int(cap),
        "eigengap_gaps": gaps,
        "lap_evals_head": [_round3(float(v)) for v in lap_evals[: min(12, n)]],
        "knn_k": int(min(knn_k, n - 1)),
    }
    if k <= 1:
        wall = time.perf_counter() - t0
        return [0] * n, meta, wall

    largest = np.argsort(evals_s)[-k:]
    embedding = evecs_s[:, largest]
    norms = np.linalg.norm(embedding, axis=1, keepdims=True)
    embedding = embedding / np.maximum(norms, 1e-12)
    km = KMeans(n_clusters=k, n_init=KMEANS_N_INIT, random_state=KMEANS_RANDOM_STATE)
    labels = [int(v) for v in km.fit_predict(embedding).tolist()]
    wall = time.perf_counter() - t0
    return labels, meta, wall


def cluster_ahc(x: np.ndarray, threshold: float) -> tuple[list[int], dict[str, Any], float]:
    t0 = time.perf_counter()
    if len(x) == 0:
        return [], {"n_windows": 0, "threshold": threshold}, 0.0
    if len(x) == 1:
        return [0], {"n_windows": 1, "threshold": threshold}, time.perf_counter() - t0
    clusterer = AgglomerativeClustering(
        metric="cosine",
        linkage="average",
        distance_threshold=threshold,
        n_clusters=None,
        compute_distances=True,
    )
    labels = [int(v) for v in clusterer.fit_predict(x).tolist()]
    distances = np.asarray(getattr(clusterer, "distances_", []), dtype=np.float64)
    knee: dict[str, Any] = {"n_windows": int(len(x)), "threshold": threshold}
    if distances.size >= 2:
        gaps = np.diff(distances)
        knee.update(
            {
                "n_merges": int(distances.size),
                "knee_gap": _round3(float(np.max(gaps))),
                "knee_merge_distance": _round3(float(distances[int(np.argmax(gaps)) + 1])),
            }
        )
    wall = time.perf_counter() - t0
    return labels, knee, wall


def consecutive_cosine(x: np.ndarray) -> np.ndarray:
    if len(x) < 2:
        return np.zeros((0,), dtype=np.float64)
    return np.sum(x[:-1] * x[1:], axis=1)


def change_indices(labels: list[int], x: np.ndarray) -> tuple[list[int], str]:
    changes = [i for i in range(len(labels) - 1) if labels[i] != labels[i + 1]]
    if changes:
        return changes, "ahc_label"
    consec = consecutive_cosine(x)
    if consec.size == 0:
        return [], "none"
    thr = float(np.percentile(consec, COSINE_DIP_PERCENTILE))
    dips = [i for i, s in enumerate(consec.tolist()) if s <= thr]
    return dips, "cosine_dip_p20"


def _remap_local_to_global(
    x: np.ndarray,
    labels: np.ndarray,
    lo: int,
    hi: int,
    local_labels: list[int],
) -> np.ndarray:
    """Map local spectral ids onto global labels; unmatched local clusters get new ids."""
    out = labels.copy()
    outside = np.ones(len(labels), dtype=bool)
    outside[lo:hi] = False
    global_ids = sorted({int(v) for v in labels[outside].tolist()}) if outside.any() else []
    centroids: dict[int, np.ndarray] = {}
    for gid in global_ids:
        rows = x[labels == gid]
        if len(rows):
            centroids[gid] = _l2_normalize(rows.mean(axis=0, keepdims=True))[0]

    max_id = int(labels.max()) if len(labels) else -1
    local_to_global: dict[int, int] = {}
    unique_local = sorted(set(int(v) for v in local_labels))
    for ll in unique_local:
        loc_idx = [lo + j for j, v in enumerate(local_labels) if int(v) == ll]
        loc_cent = _l2_normalize(x[loc_idx].mean(axis=0, keepdims=True))[0]
        best_id = None
        best_sim = -1.0
        for gid, cent in centroids.items():
            sim = float(np.dot(loc_cent, cent))
            if sim > best_sim:
                best_sim = sim
                best_id = gid
        # Match only if clearly the same speaker; else new id. Not a K prior.
        if best_id is not None and best_sim >= 0.50:
            local_to_global[ll] = best_id
        else:
            max_id += 1
            local_to_global[ll] = max_id
            centroids[max_id] = loc_cent
    for j, ll in enumerate(local_labels):
        out[lo + j] = local_to_global[int(ll)]
    return out


def _apply_local_neighborhoods(
    x: np.ndarray,
    labels: np.ndarray,
    changes: list[int],
    k_cap: int,
) -> tuple[np.ndarray, int]:
    n = len(x)
    used: set[tuple[int, int]] = set()
    applied = 0
    refined = labels.copy()
    for c in changes:
        lo = max(0, c - HYBRID_NEIGHBORHOOD)
        hi = min(n, c + 1 + HYBRID_NEIGHBORHOOD)
        key = (lo, hi)
        if key in used or hi - lo < MIN_SPECTRAL_WINDOWS:
            continue
        used.add(key)
        loc, smeta, _ = spectral_eigengap(x[lo:hi], k_cap=min(k_cap, hi - lo - 1))
        if smeta["k"] < 2:
            continue
        refined = _remap_local_to_global(x, refined, lo, hi, loc)
        applied += 1
    return refined, applied


def hybrid_m2(
    x: np.ndarray,
    ahc_labels: list[int],
    k_cap: int = K_CAP,
    mode: str = "blocks_and_local",
) -> tuple[list[int], dict[str, Any], float]:
    """Look 1 = AHC labels. Look 2 = spectral on change blocks and/or neighborhoods."""
    t0 = time.perf_counter()
    n = len(x)
    if n == 0:
        return [], {"k": 0, "change_source": "none", "mode": mode}, 0.0
    labels = np.asarray(ahc_labels, dtype=int)
    changes, source = change_indices(ahc_labels, x)

    block_meta: list[dict[str, Any]] = []
    blocks: list[tuple[int, int]] = []
    if mode == "local_only":
        refined = labels.copy()
        refined, local_applied = _apply_local_neighborhoods(x, refined, changes, k_cap)
        n_blocks = 0
    else:
        # Block re-cluster seeded by change points (full second look).
        bounds = [0] + [c + 1 for c in changes] + [n]
        next_id = 0
        block_labels = np.empty(n, dtype=int)
        for a, b in zip(bounds[:-1], bounds[1:], strict=True):
            if b <= a:
                continue
            blocks.append((a, b))
            sl = x[a:b]
            if b - a < MIN_SPECTRAL_WINDOWS:
                block_labels[a:b] = next_id
                next_id += 1
                block_meta.append({"lo": a, "hi": b, "k": 1, "reason": "short_block"})
                continue
            loc, smeta, _ = spectral_eigengap(sl, k_cap=min(k_cap, b - a - 1))
            mapping: dict[int, int] = {}
            for ll in loc:
                if ll not in mapping:
                    mapping[ll] = next_id
                    next_id += 1
            for j, ll in enumerate(loc):
                block_labels[a + j] = mapping[ll]
            block_meta.append(
                {"lo": a, "hi": b, "k": smeta["k"], "eigengap_gaps": smeta["eigengap_gaps"]}
            )
        refined, local_applied = _apply_local_neighborhoods(x, block_labels, changes, k_cap)
        n_blocks = len(blocks)

    wall = time.perf_counter() - t0
    meta = {
        "mode": mode,
        "change_source": source,
        "n_changes": len(changes),
        "n_blocks": n_blocks,
        "local_neighborhoods_applied": local_applied,
        "k_final": int(len(set(refined.tolist()))),
        "block_meta": block_meta[:24],
        "hybrid_neighborhood": HYBRID_NEIGHBORHOOD,
        "seed_threshold": HYBRID_SEED_THRESHOLD,
    }
    return [int(v) for v in refined.tolist()], meta, wall


def island_center_indices(segments: list[tuple[float, float]]) -> list[int]:
    if not segments:
        return []
    centers: list[int] = []
    start = 0
    for i in range(1, len(segments) + 1):
        gap = 0.0
        if i < len(segments):
            gap = segments[i][0] - segments[i - 1][1]
        island_break = i == len(segments) or gap > STEP_SEC * 1.5
        if island_break:
            mid = start + (i - 1 - start) // 2
            centers.append(mid)
            start = i
    return centers


def anchor_assign_m3(
    x: np.ndarray,
    segments: list[tuple[float, float]],
    k_cap: int = K_CAP,
) -> tuple[list[int], dict[str, Any], float]:
    """Cluster stable anchor windows, assign the rest to nearest centroid."""
    t0 = time.perf_counter()
    n = len(x)
    if n == 0:
        return [], {"k": 0, "n_anchors": 0}, 0.0
    if n < MIN_SPECTRAL_WINDOWS:
        wall = time.perf_counter() - t0
        return [0] * n, {"k": 1, "n_anchors": n, "fallback": "too_few_windows"}, wall

    consec = consecutive_cosine(x)
    median_c = float(np.median(consec)) if consec.size else 1.0
    anchor_mask = np.zeros(n, dtype=bool)
    if n == 1:
        anchor_mask[0] = True
    else:
        left = np.r_[1.0, consec]
        right = np.r_[consec, 1.0]
        anchor_mask = (left >= median_c) & (right >= median_c)
    for idx in island_center_indices(segments):
        if 0 <= idx < n:
            anchor_mask[idx] = True
    anchor_idx = np.where(anchor_mask)[0]
    if len(anchor_idx) < MIN_SPECTRAL_WINDOWS:
        anchor_idx = np.arange(n)
        fallback = "all_windows"
    else:
        fallback = None

    loc, smeta, _ = spectral_eigengap(x[anchor_idx], k_cap=min(k_cap, max(1, len(anchor_idx) - 1)))
    labels = np.full(n, -1, dtype=int)
    for i, lab in zip(anchor_idx.tolist(), loc, strict=True):
        labels[i] = int(lab)
    centroids: dict[int, np.ndarray] = {}
    for lab in sorted(set(loc)):
        rows = x[anchor_idx[np.array(loc) == lab]]
        centroids[int(lab)] = _l2_normalize(rows.mean(axis=0, keepdims=True))[0]
    next_id = (max(centroids) + 1) if centroids else 0
    n_assigned = 0
    n_new = 0
    for i in range(n):
        if labels[i] >= 0:
            continue
        best_lab = None
        best_sim = -1.0
        for lab, cent in centroids.items():
            sim = float(np.dot(x[i], cent))
            if sim > best_sim:
                best_sim = sim
                best_lab = lab
        if best_lab is not None and best_sim >= ANCHOR_ASSIGN_MIN_COS:
            labels[i] = best_lab
            n_assigned += 1
        else:
            labels[i] = next_id
            centroids[next_id] = x[i]
            next_id += 1
            n_new += 1
    wall = time.perf_counter() - t0
    meta = {
        "k": smeta["k"],
        "n_anchors": int(len(anchor_idx)),
        "n_assigned": n_assigned,
        "n_new_unmatched": n_new,
        "anchor_median_consec": _round3(median_c),
        "fallback": fallback,
        "eigengap_gaps": smeta["eigengap_gaps"],
        "lap_evals_head": smeta["lap_evals_head"],
    }
    return [int(v) for v in labels.tolist()], meta, wall


def labels_to_turns(
    segments: list[tuple[float, float]],
    labels: list[int],
    cfg: DiarizationConfig,
) -> list[TurnItem]:
    raw = [
        {"start": start, "end": end, "speaker": f"SPEAKER_{int(lbl):02d}"}
        for (start, end), lbl in zip(segments, labels, strict=True)
    ]
    merged = merge_turns(
        raw,
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
    return _renumber_speakers(merged)


def summarize_turns(turns: list[TurnItem]) -> dict[str, Any]:
    speech = speaker_speech(turns)
    total = sum(speech.values()) or 1e-9
    crumbs = {k: v for k, v in speech.items() if v < CRUMB_LOG_SEC}
    top1_id = max(speech, key=speech.get) if speech else None
    top1 = speech[top1_id] if top1_id else 0.0
    return {
        "n_id": len(speech),
        "crumb_count_lt3s": len(crumbs),
        "speech_sec_per_id": speech,
        "top1_id": top1_id,
        "top1_speech_sec": _round3(top1),
        "top1_share": _round3(top1 / total),
        "total_turn_speech_sec": _round3(sum(speech.values())),
    }


def overlap_interval(
    turns: list[TurnItem], start: float, end: float
) -> dict[str, Any]:
    per_id: dict[str, float] = defaultdict(float)
    hits: list[dict[str, Any]] = []
    for turn in turns:
        a = max(turn.start, start)
        b = min(turn.end, end)
        if b > a:
            dur = _round3(b - a)
            per_id[turn.speaker] += dur
            hits.append(
                {
                    "id": turn.id,
                    "speaker": turn.speaker,
                    "start": _round3(turn.start),
                    "end": _round3(turn.end),
                    "overlap_sec": dur,
                }
            )
    speech = speaker_speech(turns)
    top1 = max(speech, key=speech.get) if speech else None
    other = {k: _round3(v) for k, v in per_id.items() if k != top1}
    return {
        "interval": [start, end],
        "overlap_sec_per_id": {k: _round3(v) for k, v in sorted(per_id.items())},
        "ids_in_interval": sorted(per_id),
        "n_ids_in_interval": len(per_id),
        "non_top1_in_interval": other,
        "distinct_from_global_top1": bool(other) or (len(per_id) == 1 and top1 not in per_id),
        "turns": hits,
        "global_top1_id": top1,
        "global_speech_of_interval_ids": {k: speech.get(k, 0.0) for k in sorted(per_id)},
    }


def concat_slices(turns: list[TurnItem], duration: float) -> list[dict[str, Any]]:
    rows = []
    t = 0.0
    idx = 0
    while t < duration - 1e-9:
        t1 = min(duration, t + CONCAT_SLICE_SEC)
        per_id: dict[str, float] = defaultdict(float)
        for turn in turns:
            a = max(turn.start, t)
            b = min(turn.end, t1)
            if b > a:
                per_id[turn.speaker] += b - a
        total = sum(per_id.values()) or 1e-9
        top1_id = max(per_id, key=per_id.get) if per_id else None
        rows.append(
            {
                "slice_index": idx,
                "offset_sec": _round3(t),
                "end_sec": _round3(t1),
                "clip_hint": {0: "clip01", 1: "clip02", 2: "clip03"}.get(idx),
                "n_id": len(per_id),
                "speech_sec_per_id": {k: _round3(v) for k, v in sorted(per_id.items())},
                "top1_id": top1_id,
                "top1_share": _round3((per_id[top1_id] if top1_id else 0.0) / total),
            }
        )
        t = t1
        idx += 1
    return rows


def dump_timeline(path: Path, turns: list[TurnItem], extra: dict[str, Any]) -> None:
    payload = {
        "schema_version": "1",
        **extra,
        "turns": [
            {"id": t.id, "start": _round3(t.start), "end": _round3(t.end), "speaker": t.speaker}
            for t in turns
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def copy_clip(clip_id: str, src: Path) -> Path:
    dest_dir = WORK / clip_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "audio.wav"
    if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    return dest


def window_trace(
    segments: list[tuple[float, float]],
    labels: list[int],
    x: np.ndarray,
    start: float,
    end: float,
) -> list[dict[str, Any]]:
    consec = consecutive_cosine(x)
    rows = []
    for i, ((s, e), lab) in enumerate(zip(segments, labels, strict=True)):
        if e < start or s > end:
            continue
        prev = float(consec[i - 1]) if i > 0 and i - 1 < len(consec) else None
        rows.append(
            {
                "i": i,
                "start": _round3(s),
                "end": _round3(e),
                "label": int(lab),
                "cosine_to_prev": _round3(prev) if prev is not None else None,
            }
        )
    return rows


def cluster_all_methods(
    x: np.ndarray,
    segments: list[tuple[float, float]],
    cfg: DiarizationConfig,
) -> dict[str, dict[str, Any]]:
    """Cluster once-computed embeddings with M0/M1/M2/M3. Returns method → payload."""
    out: dict[str, dict[str, Any]] = {}
    ahc_cache: dict[float, tuple[list[int], dict[str, Any], float]] = {}
    for thr in AHC_THRESHOLDS:
        labels, meta, wall = cluster_ahc(x, thr)
        ahc_cache[thr] = (labels, meta, wall)
        key = f"M0_thr{thr:.2f}"
        out[key] = {"method": "M0", "threshold": thr, "labels": labels, "meta": meta, "cluster_sec": wall}

    labels_m1, meta_m1, wall_m1 = spectral_eigengap(x, k_cap=K_CAP)
    out["M1_spectral"] = {
        "method": "M1",
        "labels": labels_m1,
        "meta": meta_m1,
        "cluster_sec": wall_m1,
    }

    seed_labels = ahc_cache[HYBRID_SEED_THRESHOLD][0]
    labels_m2, meta_m2, wall_m2 = hybrid_m2(x, seed_labels, k_cap=K_CAP, mode="blocks_and_local")
    out["M2_hybrid"] = {
        "method": "M2",
        "seed_threshold": HYBRID_SEED_THRESHOLD,
        "labels": labels_m2,
        "meta": meta_m2,
        "cluster_sec": wall_m2,
    }

    labels_m2_local, meta_m2_local, wall_m2_local = hybrid_m2(
        x, seed_labels, k_cap=K_CAP, mode="local_only"
    )
    out["M2_local"] = {
        "method": "M2",
        "seed_threshold": HYBRID_SEED_THRESHOLD,
        "labels": labels_m2_local,
        "meta": meta_m2_local,
        "cluster_sec": wall_m2_local,
    }

    seed80 = ahc_cache[0.80][0]
    labels_m2b, meta_m2b, wall_m2b = hybrid_m2(x, seed80, k_cap=K_CAP, mode="blocks_and_local")
    meta_m2b = dict(meta_m2b)
    meta_m2b["seed_threshold"] = 0.80
    out["M2_hybrid_seed0.80"] = {
        "method": "M2",
        "seed_threshold": 0.80,
        "labels": labels_m2b,
        "meta": meta_m2b,
        "cluster_sec": wall_m2b,
    }

    labels_m3, meta_m3, wall_m3 = anchor_assign_m3(x, segments, k_cap=K_CAP)
    out["M3_anchor"] = {
        "method": "M3",
        "labels": labels_m3,
        "meta": meta_m3,
        "cluster_sec": wall_m3,
    }
    return out


def quality_row(
    clip_id: str,
    method_key: str,
    payload: dict[str, Any],
    segments: list[tuple[float, float]],
    x: np.ndarray,
    duration: float,
    embed_sec: float,
    cfg: DiarizationConfig,
) -> dict[str, Any]:
    labels: list[int] = payload["labels"]
    turns = labels_to_turns(segments, labels, cfg)
    stats = summarize_turns(turns)
    dump_timeline(
        TIMELINES / f"{clip_id}__{method_key}.json",
        turns,
        {
            "clip": clip_id,
            "method": method_key,
            "n_windows": int(len(segments)),
            "cluster_meta": {k: v for k, v in payload.get("meta", {}).items() if k != "block_meta"},
        },
    )
    row: dict[str, Any] = {
        "clip": clip_id,
        "method": method_key,
        "family": payload["method"],
        "n_windows": int(len(segments)),
        "embed_sec": _round3(embed_sec),
        "cluster_sec": _round3(float(payload["cluster_sec"])),
        "duration_sec": duration,
        "raw_n_labels": int(len(set(labels))) if labels else 0,
        "cluster_meta": payload.get("meta", {}),
        **stats,
    }
    if clip_id == "clip01":
        row["greeting_42_45"] = overlap_interval(turns, GREETING_START, GREETING_END)
        row["window_trace_40_48"] = window_trace(segments, labels, x, 40.0, 48.0)
    if clip_id == "concat_01_02_03":
        row["slices"] = concat_slices(turns, duration)
    return row


def main() -> None:
    t_all = time.perf_counter()
    rss = RssSampler()
    rss.start()
    OUT.mkdir(parents=True, exist_ok=True)
    TIMELINES.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    vad_cfg, diar_cfg = load_vad_diar_cfg()
    if abs(diar_cfg.embed.window_sec - WINDOW_SEC) > 1e-9 or abs(diar_cfg.embed.step_sec - STEP_SEC) > 1e-9:
        raise RuntimeError(
            f"Expected frozen windows {WINDOW_SEC}/{STEP_SEC}, got "
            f"{diar_cfg.embed.window_sec}/{diar_cfg.embed.step_sec}"
        )
    min_embed = diar_cfg.embed.min_sec
    premerge = diar_cfg.merge.vad_premerge_gap_sec

    all_clips = QUALITY_CLIPS + [TIMING_CLIP]
    for clip_id, src in all_clips:
        if not src.is_file():
            raise FileNotFoundError(f"Packed wav missing: {src}")

    detector = SileroVadDetector()
    vad_rows: dict[str, Any] = {}
    audio_cache: dict[str, tuple[np.ndarray, int, list[Interval], float]] = {}

    for clip_id, src in all_clips:
        wav = copy_clip(clip_id, src)
        print(f"VAD {clip_id}…", flush=True)
        speech = detector.detect(wav, vad_cfg, job_id=clip_id)
        audio, sr = sf.read(str(wav))
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        duration = _round3(float(len(audio) / sr))
        islands = merge_speech_regions(
            [Interval(start=r.start, end=r.end) for r in speech.regions],
            max_gap_sec=premerge,
            min_duration_sec=min_embed,
        )
        audio_cache[clip_id] = (audio, sr, islands, duration)
        vad_rows[clip_id] = {
            "duration_sec": duration,
            "n_regions": len(speech.regions),
            "n_islands": len(islands),
            "speech_sec": speech.speech_sec,
            "vad_runtime_sec": speech.runtime_sec,
        }

    print("Loading WeSpeaker embedder (wespeaker-resnet34)…", flush=True)
    t_load = time.perf_counter()
    embedder = SpeakerEmbedder(model="wespeaker-resnet34")
    model_load_sec = _round3(time.perf_counter() - t_load)
    print(f"model_load_sec={model_load_sec}", flush=True)

    timing_id, _timing_src = TIMING_CLIP
    audio, sr, islands, duration = audio_cache[timing_id]
    print(f"embed {timing_id} pass1…", flush=True)
    seg1, x1, embed1 = window_embeddings(audio, sr, islands, embedder, WINDOW_SEC, STEP_SEC, min_embed)
    methods_p1 = cluster_all_methods(x1, seg1, diar_cfg)
    print(f"embed {timing_id} pass2 (warm)…", flush=True)
    seg2, x2, embed2 = window_embeddings(audio, sr, islands, embedder, WINDOW_SEC, STEP_SEC, min_embed)
    methods_p2 = cluster_all_methods(x2, seg2, diar_cfg)

    def cluster_sec_map(methods: dict[str, dict[str, Any]]) -> dict[str, float]:
        return {k: _round3(float(v["cluster_sec"])) for k, v in methods.items()}

    timing_5min = {
        "duration_sec": duration,
        "pass1": {
            "embed_sec": _round3(embed1),
            "n_windows": int(len(seg1)),
            "cluster_sec": cluster_sec_map(methods_p1),
            "n_id": {k: int(len(set(v["labels"]))) if v["labels"] else 0 for k, v in methods_p1.items()},
        },
        "pass2": {
            "embed_sec": _round3(embed2),
            "n_windows": int(len(seg2)),
            "cluster_sec": cluster_sec_map(methods_p2),
            "n_id": {k: int(len(set(v["labels"]))) if v["labels"] else 0 for k, v in methods_p2.items()},
        },
    }

    embed_cache: dict[str, dict[str, Any]] = {}
    quality_rows: list[dict[str, Any]] = []

    for clip_id, _src in QUALITY_CLIPS:
        audio, sr, islands, duration = audio_cache[clip_id]
        print(f"embed {clip_id}…", flush=True)
        segments, x, embed_wall = window_embeddings(
            audio, sr, islands, embedder, WINDOW_SEC, STEP_SEC, min_embed
        )
        embed_cache[clip_id] = {
            "segments": segments,
            "n_windows": int(len(segments)),
            "embed_sec": _round3(embed_wall),
        }
        methods = cluster_all_methods(x, segments, diar_cfg)
        for method_key, payload in methods.items():
            quality_rows.append(
                quality_row(clip_id, method_key, payload, segments, x, duration, embed_wall, diar_cfg)
            )

    concat_embed = embed_cache["concat_01_02_03"]
    peak_kb = rss.stop()
    wall_sec = _round3(time.perf_counter() - t_all)
    results = {
        "schema_version": "1",
        "experiment": "D5.diar-spectral",
        "model": "wespeaker-resnet34",
        "window_sec": WINDOW_SEC,
        "step_sec": STEP_SEC,
        "k_cap": K_CAP,
        "knn_k": KNN_K,
        "onnx_threads": ONNX_THREADS,
        "model_load_sec": model_load_sec,
        "ahc_thresholds": list(AHC_THRESHOLDS),
        "hybrid_seed_threshold": HYBRID_SEED_THRESHOLD,
        "greeting_interval_sec": [GREETING_START, GREETING_END],
        "notes": [
            "No crumb merge applied; crumb_count_lt3s is log-only.",
            "Eigengap may choose K=1; K is not forced into [2,4].",
            "Production merge_turns (gap 0.3 / absorb 1.0s) still applied after labels.",
        ],
        "merge": {
            "same_speaker_gap_sec": diar_cfg.merge.same_speaker_gap_sec,
            "absorb_turn_shorter_than_sec": diar_cfg.merge.absorb_turn_shorter_than_sec,
            "vad_premerge_gap_sec": diar_cfg.merge.vad_premerge_gap_sec,
            "min_embed_sec": min_embed,
        },
        "vad": vad_rows,
        "timing_5min": timing_5min,
        "timing_concat": {
            "embed_sec": concat_embed["embed_sec"],
            "n_windows": concat_embed["n_windows"],
            "duration_sec": vad_rows["concat_01_02_03"]["duration_sec"],
        },
        "quality": quality_rows,
        "wall_sec": wall_sec,
        "peak_rss_mb": _round3(peak_kb / 1024.0),
    }
    (OUT / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        f"Wrote {OUT / 'results.json'} wall_sec={wall_sec} "
        f"peak_rss_mb={results['peak_rss_mb']} model_load_sec={model_load_sec}",
        flush=True,
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Throwaway D5.diar-twopass research runner (not production pipeline).

Stage 1: Silero islands → glue units <1 s → 1A WeSpeaker adjacent cosine /
1B cheap-feature adjacent / 1C cheap change-point + cheap spectral.
Stage 2: WeSpeaker 2A overlap 1.5/0.75, 2B no-overlap 1.5/1.5, 2C one embed
per glued unit. No eval/gold, no crumb-primary, no K in [2,4] prior, no
second DNN, no ASR/LLM, no src/ edits.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

import numpy as np
import onnxruntime as ort
import soundfile as sf
import yaml
from scipy.fft import dct
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
WORK = Path("/tmp/d5-diar-twopass")
TIMELINES = OUT / "timelines"

GLUE_SEC = 1.0
WINDOW_2A = 1.5
STEP_2A = 0.75
WINDOW_2B = 1.5
AHC_THRESHOLD = 0.85
# 1A: merge adjacent units if WeSpeaker cosine similarity >= threshold.
COSINE_1A = (0.40, 0.55, 0.70)
# 1B/1C: merge/keep or split on cheap-feature cosine similarity (not WeSpeaker).
COSINE_CHEAP = (0.80, 0.90, 0.96)
LONG_UNIT_SEC = 3.0
CHEAP_WIN_SEC = 0.75
CHEAP_STEP_SEC = 0.75
N_FFT = 512
HOP = 160
N_MELS = 24
N_MFCC = 13
K_CAP = 20
KNN_K = 10
KMEANS_RANDOM_STATE = 0
KMEANS_N_INIT = 10
CRUMB_LOG_SEC = 3.0
GREETING_START = 42.0
GREETING_END = 45.0
CONCAT_SLICE_SEC = 60.0
DUR_BINS = (0.0, 0.5, 1.0, 2.0, 4.0, 8.0, 16.0, float("inf"))
DUR_LABELS = ("0-0.5", "0.5-1", "1-2", "2-4", "4-8", "8-16", "16+")

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


class CountingEmbedder:
    """Wrap SpeakerEmbedder and count embed() calls / wall."""

    def __init__(self, inner: SpeakerEmbedder) -> None:
        self.inner = inner
        self.n_calls = 0
        self.embed_sec = 0.0

    def reset(self) -> None:
        self.n_calls = 0
        self.embed_sec = 0.0

    def embed(self, audio: np.ndarray) -> np.ndarray:
        self.n_calls += 1
        t0 = time.perf_counter()
        out = self.inner.embed(audio)
        self.embed_sec += time.perf_counter() - t0
        return np.asarray(out, dtype=np.float64)


def _round3(value: float) -> float:
    return round(float(value), 3)


def _round1(value: float) -> float:
    return round(float(value), 1)


def load_vad_diar_cfg() -> tuple[VadConfig, DiarizationConfig]:
    """Load vad + diarization from YAML without touching .env."""
    base = yaml.safe_load((ROOT / "config" / "base.yaml").read_text(encoding="utf-8"))
    demo = yaml.safe_load((ROOT / "config" / "profiles" / "demo.yaml").read_text(encoding="utf-8"))
    merged = deep_merge(base, demo)
    return (
        VadConfig.model_validate(merged["vad"]),
        DiarizationConfig.model_validate(merged["diarization"]),
    )


def copy_clip(clip_id: str, src: Path) -> Path:
    dest_dir = WORK / clip_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "audio.wav"
    if not dest.is_file() or dest.stat().st_size != src.stat().st_size:
        shutil.copy2(src, dest)
    return dest


def duration_histogram(values: list[float]) -> dict[str, int]:
    counts = {lab: 0 for lab in DUR_LABELS}
    for dur in values:
        for lo, hi, lab in zip(DUR_BINS[:-1], DUR_BINS[1:], DUR_LABELS, strict=True):
            if lo <= dur < hi:
                counts[lab] += 1
                break
    return counts


def glue_units(islands: list[Interval], glue_sec: float) -> list[list[Interval]]:
    """Attach islands shorter than glue_sec to neighbors.

    - short with a previous unit → append to previous
    - leading shorts → merge into the next (large) island
    - a run of shorts with no large neighbor → one unit
    """
    if not islands:
        return []
    n = len(islands)
    is_small = [isl.duration < glue_sec for isl in islands]
    units: list[list[Interval]] = []
    i = 0
    while i < n:
        if not is_small[i]:
            units.append([islands[i]])
            i += 1
            continue
        j = i
        while j < n and is_small[j]:
            j += 1
        run = islands[i:j]
        if units:
            units[-1].extend(run)
        elif j < n:
            units.append(run + [islands[j]])
            i = j + 1
            continue
        else:
            units.append(run)
        i = j
    return units


def unit_span(unit: list[Interval]) -> tuple[float, float]:
    return unit[0].start, unit[-1].end


def unit_speech_sec(unit: list[Interval]) -> float:
    return sum(isl.duration for isl in unit)


def concat_unit_audio(audio: np.ndarray, sr: int, unit: list[Interval]) -> np.ndarray:
    parts: list[np.ndarray] = []
    for isl in unit:
        a = int(isl.start * sr)
        b = int(isl.end * sr)
        if b > a:
            parts.append(audio[a:b])
    if not parts:
        return np.zeros((0,), dtype=audio.dtype)
    return np.concatenate(parts)


def hz_to_mel(hz: np.ndarray | float) -> np.ndarray | float:
    return 2595.0 * np.log10(1.0 + np.asarray(hz) / 700.0)


def mel_to_hz(mel: np.ndarray | float) -> np.ndarray | float:
    return 700.0 * (10.0 ** (np.asarray(mel) / 2595.0) - 1.0)


def mel_filterbank(sr: int, n_fft: int, n_mels: int) -> np.ndarray:
    n_freqs = n_fft // 2 + 1
    low = float(hz_to_mel(0.0))
    high = float(hz_to_mel(sr / 2.0))
    mels = np.linspace(low, high, n_mels + 2)
    hz = np.asarray(mel_to_hz(mels), dtype=np.float64)
    bins = np.floor((n_fft + 1) * hz / sr).astype(int)
    fb = np.zeros((n_mels, n_freqs), dtype=np.float64)
    for m in range(n_mels):
        left, center, right = bins[m], bins[m + 1], bins[m + 2]
        if center == left:
            center += 1
        if right == center:
            right += 1
        for k in range(left, min(center, n_freqs)):
            fb[m, k] = (k - left) / max(center - left, 1)
        for k in range(center, min(right, n_freqs)):
            fb[m, k] = (right - k) / max(right - center, 1)
    return fb


_MEL_FB: np.ndarray | None = None


def _mel_fb(sr: int) -> np.ndarray:
    global _MEL_FB
    if _MEL_FB is None:
        _MEL_FB = mel_filterbank(sr, N_FFT, N_MELS)
    return _MEL_FB


def cheap_vector(audio: np.ndarray, sr: int) -> np.ndarray:
    """Mean/std MFCC + flux + log-RMS + centroid. Numpy/scipy only (no WeSpeaker)."""
    x = np.asarray(audio, dtype=np.float64)
    if x.size < 64:
        x = np.pad(x, (0, 64 - x.size))
    frame = N_FFT
    hop = HOP
    if x.size < frame:
        x = np.pad(x, (0, frame - x.size))
    n_frames = 1 + (x.size - frame) // hop
    window = np.hanning(frame)
    frames = np.stack([x[i * hop : i * hop + frame] * window for i in range(n_frames)])
    mag = np.abs(np.fft.rfft(frames, n=N_FFT, axis=1))
    fb = _mel_fb(sr)
    logmel = np.log(np.maximum(mag @ fb.T, 1e-8))
    mfcc = np.asarray(dct(logmel, type=2, axis=1, norm="ortho")[:, :N_MFCC], dtype=np.float64)
    mfcc_mean = mfcc.mean(axis=0)
    mfcc_std = mfcc.std(axis=0)
    spec = mag / np.maximum(mag.sum(axis=1, keepdims=True), 1e-9)
    diff = np.diff(spec, axis=0)
    flux = float(np.mean(np.sqrt(np.sum(np.clip(diff, 0.0, None) ** 2, axis=1)))) if len(spec) > 1 else 0.0
    rms = float(np.sqrt(np.mean(x**2)))
    freqs = np.linspace(0.0, sr / 2.0, mag.shape[1])
    centroid = float(np.mean((mag * freqs).sum(axis=1) / np.maximum(mag.sum(axis=1), 1e-9)))
    vec = np.concatenate(
        [mfcc_mean, mfcc_std, np.array([flux, np.log(rms + 1e-8), centroid / (sr / 2.0)])]
    )
    return vec / max(float(np.linalg.norm(vec)), 1e-12)


def cosine_knn_affinity(x: np.ndarray, knn_k: int = KNN_K) -> np.ndarray:
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
    n = int(lap_evals.size)
    if n <= 1:
        return 1, []
    cap = min(int(k_cap), n - 1)
    if cap < 1:
        return 1, []
    gaps = np.diff(lap_evals[: cap + 1])
    k = int(np.argmax(gaps) + 1)
    return k, [_round3(float(g)) for g in gaps]


def spectral_eigengap(x: np.ndarray, k_cap: int = K_CAP, knn_k: int = KNN_K) -> tuple[list[int], dict[str, Any], float]:
    t0 = time.perf_counter()
    n = len(x)
    if n == 0:
        return [], {"k": 0, "n_windows": 0}, 0.0
    if n == 1:
        return [0], {"k": 1, "n_windows": 1}, time.perf_counter() - t0
    affinity = cosine_knn_affinity(x, knn_k=knn_k)
    degree = np.maximum(affinity.sum(axis=1), 1e-12)
    inv_sqrt = 1.0 / np.sqrt(degree)
    norm_aff = 0.5 * ((affinity * inv_sqrt[:, None] * inv_sqrt[None, :]) + (affinity * inv_sqrt[:, None] * inv_sqrt[None, :]).T)
    evals_s, evecs_s = np.linalg.eigh(norm_aff)
    lap_evals = np.sort(1.0 - evals_s[::-1])
    cap = min(int(k_cap), n - 1)
    k, gaps = eigengap_k(lap_evals, cap)
    meta: dict[str, Any] = {
        "k": int(k),
        "n_windows": int(n),
        "k_cap": int(cap),
        "eigengap_gaps": gaps,
        "feature": "cheap_or_wespeaker_caller_must_label",
    }
    if k <= 1:
        return [0] * n, meta, time.perf_counter() - t0
    largest = np.argsort(evals_s)[-k:]
    embedding = evecs_s[:, largest]
    norms = np.linalg.norm(embedding, axis=1, keepdims=True)
    embedding = embedding / np.maximum(norms, 1e-12)
    km = KMeans(n_clusters=k, n_init=KMEANS_N_INIT, random_state=KMEANS_RANDOM_STATE)
    labels = [int(v) for v in km.fit_predict(embedding).tolist()]
    return labels, meta, time.perf_counter() - t0


def cluster_ahc(x: np.ndarray, threshold: float) -> tuple[list[int], dict[str, Any], float]:
    t0 = time.perf_counter()
    if len(x) == 0:
        return [], {"n": 0, "threshold": threshold}, 0.0
    if len(x) == 1:
        return [0], {"n": 1, "threshold": threshold}, time.perf_counter() - t0
    clusterer = AgglomerativeClustering(
        metric="cosine",
        linkage="average",
        distance_threshold=threshold,
        n_clusters=None,
    )
    labels = [int(v) for v in clusterer.fit_predict(x).tolist()]
    return labels, {"n": int(len(x)), "threshold": threshold, "n_labels": len(set(labels))}, time.perf_counter() - t0


def speaker_speech(turns: list[TurnItem]) -> dict[str, float]:
    out: dict[str, float] = defaultdict(float)
    for turn in turns:
        out[turn.speaker] += turn.end - turn.start
    return {k: _round3(v) for k, v in sorted(out.items())}


def labels_to_turns(
    segments: list[tuple[float, float]],
    labels: list[int],
    cfg: DiarizationConfig,
    *,
    absorb: bool,
) -> list[TurnItem]:
    raw = [
        {"start": start, "end": end, "speaker": f"SPEAKER_{int(lbl):02d}"}
        for (start, end), lbl in zip(segments, labels, strict=True)
    ]
    merged = merge_turns(
        raw,
        same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
        absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec if absorb else 0.0,
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


def sequential_labels_from_adjacent(sims: list[float], thr: float) -> list[int]:
    if not sims:
        return [0]
    labels = [0]
    for sim in sims:
        labels.append(labels[-1] if sim >= thr else labels[-1] + 1)
    return labels


def fill_missing_labels(labels: list[int | None]) -> list[int]:
    """Nearest-in-time fill for units too short to embed."""
    n = len(labels)
    filled: list[int] = []
    last = 0
    for i, lab in enumerate(labels):
        if lab is not None:
            last = int(lab)
            filled.append(last)
            continue
        nxt = None
        for j in range(i + 1, n):
            if labels[j] is not None:
                nxt = int(labels[j])
                break
        filled.append(int(nxt) if nxt is not None else last)
    if not filled:
        return []
    return filled


def production_windows(island: Interval, window_sec: float, step_sec: float, min_embed: float) -> list[tuple[float, float]]:
    """Same short-island shortcut as WeSpeakerDiarizer.diarize."""
    dur = island.duration
    if dur < min_embed:
        return []
    if dur <= window_sec + step_sec:
        return [(island.start, island.end)]
    segs: list[tuple[float, float]] = []
    t = island.start
    while t + window_sec <= island.end + 1e-12:
        segs.append((t, t + window_sec))
        t += step_sec
    if island.end - t >= min_embed:
        segs.append((t, island.end))
    return segs


def nonoverlap_windows(island: Interval, window_sec: float, min_embed: float) -> list[tuple[float, float]]:
    """Strict tiles, no overlap; island <= window → one window."""
    dur = island.duration
    if dur < min_embed:
        return []
    if dur <= window_sec:
        return [(island.start, island.end)]
    segs: list[tuple[float, float]] = []
    t = island.start
    while t + window_sec <= island.end + 1e-12:
        segs.append((t, t + window_sec))
        t += window_sec
    if island.end - t >= min_embed:
        segs.append((t, island.end))
    return segs


def embed_segments(
    audio: np.ndarray,
    sr: int,
    segments: list[tuple[float, float]],
    embedder: CountingEmbedder,
    min_embed: float,
) -> tuple[list[tuple[float, float]], np.ndarray]:
    kept: list[tuple[float, float]] = []
    rows: list[np.ndarray] = []
    for start, end in segments:
        if end - start < min_embed:
            continue
        a = int(start * sr)
        b = int(end * sr)
        sl = audio[a:b]
        if sl.size < int(min_embed * sr):
            continue
        rows.append(embedder.embed(sl))
        kept.append((round(start, 3), round(end, 3)))
    if not rows:
        return kept, np.zeros((0, 1), dtype=np.float64)
    return kept, _l2_normalize(np.stack(rows))


def summarize_turns(turns: list[TurnItem]) -> dict[str, Any]:
    speech = speaker_speech(turns)
    total = sum(speech.values()) or 1e-9
    crumbs = {k: v for k, v in speech.items() if v < CRUMB_LOG_SEC}
    top1_id = max(speech, key=speech.get) if speech else None
    top1 = speech[top1_id] if top1_id else 0.0
    shortest = min(speech.values()) if speech else 0.0
    return {
        "n_id": len(speech),
        "crumb_count_lt3s": len(crumbs),
        "speech_sec_per_id": speech,
        "top1_id": top1_id,
        "top1_speech_sec": _round3(top1),
        "top1_share": _round3(top1 / total),
        "shortest_id_speech_sec": _round3(float(shortest)),
        "total_turn_speech_sec": _round3(sum(speech.values())),
    }


def overlap_interval(turns: list[TurnItem], start: float, end: float) -> dict[str, Any]:
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


def island_subwindows(islands: list[Interval], window_sec: float, step_sec: float, min_embed: float) -> list[tuple[float, float]]:
    segs: list[tuple[float, float]] = []
    for isl in islands:
        if isl.duration < min_embed:
            continue
        if isl.duration <= window_sec:
            segs.append((isl.start, isl.end))
            continue
        t = isl.start
        while t + window_sec <= isl.end + 1e-12:
            segs.append((t, t + window_sec))
            t += step_sec
        if isl.end - t >= min_embed:
            segs.append((t, isl.end))
    return segs


def adjacent_cosines(x: np.ndarray) -> list[float]:
    if len(x) < 2:
        return []
    return [float(np.dot(x[i], x[i + 1])) for i in range(len(x) - 1)]


def sim_stats(values: list[float]) -> dict[str, float]:
    if not values:
        return {"n": 0}
    arr = np.asarray(values, dtype=np.float64)
    return {
        "n": int(arr.size),
        "min": _round3(float(arr.min())),
        "p10": _round3(float(np.percentile(arr, 10))),
        "median": _round3(float(np.median(arr))),
        "p90": _round3(float(np.percentile(arr, 90))),
        "max": _round3(float(arr.max())),
        "mean": _round3(float(arr.mean())),
    }


def method_row(
    clip_id: str,
    method: str,
    turns: list[TurnItem],
    extra: dict[str, Any],
    duration: float,
    dump: bool,
) -> dict[str, Any]:
    summary = summarize_turns(turns)
    row: dict[str, Any] = {"clip": clip_id, "method": method, **summary, **extra}
    if clip_id == "clip01":
        row["greeting_42_45"] = overlap_interval(turns, GREETING_START, GREETING_END)
    if clip_id == "concat_01_02_03":
        row["concat_slices"] = concat_slices(turns, duration)
    if dump:
        dump_timeline(TIMELINES / f"{clip_id}__{method}.json", turns, row)
    return row


def preprocess_clip(
    wav: Path,
    vad: SileroVadDetector,
    vad_cfg: VadConfig,
    diar_cfg: DiarizationConfig,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    speech = vad.detect(wav, vad_cfg, job_id=wav.parent.name)
    vad_sec = time.perf_counter() - t0
    regions = [Interval(start=r.start, end=r.end) for r in speech.regions]
    islands = merge_speech_regions(
        regions,
        max_gap_sec=diar_cfg.merge.vad_premerge_gap_sec,
        min_duration_sec=0.0,
    )
    units = glue_units(islands, GLUE_SEC)
    island_durs = [isl.duration for isl in islands]
    unit_speech = [unit_speech_sec(u) for u in units]
    unit_spans = [unit_span(u)[1] - unit_span(u)[0] for u in units]
    greeting_units = []
    for i, u in enumerate(units):
        s, e = unit_span(u)
        if e > GREETING_START and s < GREETING_END:
            greeting_units.append(
                {
                    "unit_index": i,
                    "start": _round3(s),
                    "end": _round3(e),
                    "n_islands": len(u),
                    "speech_sec": _round3(unit_speech_sec(u)),
                    "covers_full_greeting": s <= GREETING_START and e >= GREETING_END,
                }
            )
    return {
        "vad_sec": _round3(vad_sec),
        "n_regions": len(regions),
        "n_islands": len(islands),
        "n_units": len(units),
        "n_islands_lt_1s": sum(1 for d in island_durs if d < GLUE_SEC),
        "speech_sec": _round3(sum(island_durs)),
        "island_duration_hist": duration_histogram(island_durs),
        "unit_speech_hist": duration_histogram(unit_speech),
        "unit_span_hist": duration_histogram(unit_spans),
        "island_durations": [_round3(d) for d in island_durs],
        "unit_speech_durations": [_round3(d) for d in unit_speech],
        "units": [
            {
                "i": i,
                "start": _round3(unit_span(u)[0]),
                "end": _round3(unit_span(u)[1]),
                "speech_sec": _round3(unit_speech_sec(u)),
                "n_islands": len(u),
                "islands": [{"start": _round3(x.start), "end": _round3(x.end)} for x in u],
            }
            for i, u in enumerate(units)
        ],
        "greeting_units_clip01": greeting_units,
        "regions": regions,
        "islands": islands,
        "unit_lists": units,
        "speech_artifact_runtime_sec": speech.runtime_sec,
    }


def embed_units(
    audio: np.ndarray,
    sr: int,
    units: list[list[Interval]],
    embedder: CountingEmbedder,
    min_embed: float,
) -> tuple[list[np.ndarray | None], int]:
    vecs: list[np.ndarray | None] = []
    n_ok = 0
    for unit in units:
        sl = concat_unit_audio(audio, sr, unit)
        if sl.size < int(min_embed * sr):
            vecs.append(None)
            continue
        vecs.append(_l2_normalize(np.asarray(embedder.embed(sl), dtype=np.float64).reshape(1, -1))[0])
        n_ok += 1
    return vecs, n_ok


def stacked_ok(vecs: list[np.ndarray | None]) -> tuple[np.ndarray, list[int]]:
    idx = [i for i, v in enumerate(vecs) if v is not None]
    if not idx:
        return np.zeros((0, 1), dtype=np.float64), []
    return np.stack([vecs[i] for i in idx]), idx


def island_segments_with_unit_labels(
    units: list[list[Interval]],
    unit_labels: list[int],
) -> tuple[list[tuple[float, float]], list[int]]:
    segs: list[tuple[float, float]] = []
    labs: list[int] = []
    for unit, lab in zip(units, unit_labels, strict=True):
        for isl in unit:
            segs.append((round(isl.start, 3), round(isl.end, 3)))
            labs.append(int(lab))
    return segs, labs


def run_methods_for_clip(
    clip_id: str,
    wav: Path,
    audio: np.ndarray,
    sr: int,
    duration: float,
    prep: dict[str, Any],
    embedder: CountingEmbedder,
    diar_cfg: DiarizationConfig,
    dump: bool,
) -> dict[str, Any]:
    islands: list[Interval] = prep["islands"]
    units: list[list[Interval]] = prep["unit_lists"]
    min_embed = diar_cfg.embed.min_sec
    out_methods: dict[str, Any] = {}

    # --- unit WeSpeaker embeds (shared 1A / 2C) ---
    embedder.reset()
    t_unit = time.perf_counter()
    unit_vecs, n_unit_ok = embed_units(audio, sr, units, embedder, min_embed)
    unit_embed_wall = time.perf_counter() - t_unit
    n_unit_calls = embedder.n_calls
    unit_embed_sec = embedder.embed_sec
    x_units, unit_ok_idx = stacked_ok(unit_vecs)
    unit_sims = adjacent_cosines(
        np.stack([unit_vecs[i] for i in range(len(unit_vecs)) if unit_vecs[i] is not None])
        if n_unit_ok >= 2
        else np.zeros((0, 1))
    )
    # Adjacent sims in unit order (skip missing by filling from kept sequence).
    ordered_unit_x = []
    for v in unit_vecs:
        if v is not None:
            ordered_unit_x.append(v)
    unit_adj = adjacent_cosines(np.stack(ordered_unit_x) if ordered_unit_x else np.zeros((0, 1)))

    cheap_unit_vecs = []
    t_cheap_u = time.perf_counter()
    for unit in units:
        sl = concat_unit_audio(audio, sr, unit)
        cheap_unit_vecs.append(cheap_vector(sl, sr) if sl.size else np.zeros(2 * N_MFCC + 3))
    cheap_unit_sec = time.perf_counter() - t_cheap_u
    cheap_x = _l2_normalize(np.stack(cheap_unit_vecs)) if cheap_unit_vecs else np.zeros((0, 1))
    cheap_adj = adjacent_cosines(cheap_x)

    # 1A
    for thr in COSINE_1A:
        labels_kept = sequential_labels_from_adjacent(unit_adj, thr)
        mapped: list[int | None] = [None] * len(units)
        for j, i in enumerate(unit_ok_idx):
            mapped[i] = labels_kept[j] if j < len(labels_kept) else labels_kept[-1]
        if not unit_ok_idx and units:
            mapped = [0] * len(units)
        # If some units lacked embeds, sequential labels were over ok-units only.
        full = fill_missing_labels(mapped)
        segs, labs = island_segments_with_unit_labels(units, full)
        t_cl = time.perf_counter()
        turns = labels_to_turns(segs, labs, diar_cfg, absorb=False)
        cluster_sec = time.perf_counter() - t_cl
        key = f"1A_cos{thr:.2f}"
        out_methods[key] = method_row(
            clip_id,
            key,
            turns,
            {
                "stage": 1,
                "n_embed_calls": n_unit_calls,
                "embed_sec": _round3(unit_embed_sec),
                "cluster_sec": _round3(cluster_sec),
                "n_units": len(units),
                "n_units_embedded": n_unit_ok,
                "cosine_threshold": thr,
                "feature": "wespeaker_unit",
            },
            duration,
            dump,
        )

    # 1B cheap adjacent
    for thr in COSINE_CHEAP:
        labels = sequential_labels_from_adjacent(cheap_adj, thr) if len(units) else []
        if len(labels) < len(units):
            labels = (labels + [labels[-1] if labels else 0] * len(units))[: len(units)]
        segs, labs = island_segments_with_unit_labels(units, labels if labels else [0] * len(units))
        t_cl = time.perf_counter()
        turns = labels_to_turns(segs, labs, diar_cfg, absorb=False)
        cluster_sec = time.perf_counter() - t_cl
        key = f"1B_cheap_cos{thr:.2f}"
        out_methods[key] = method_row(
            clip_id,
            key,
            turns,
            {
                "stage": 1,
                "n_embed_calls": 0,
                "embed_sec": 0.0,
                "cluster_sec": _round3(cluster_sec),
                "cheap_feature_sec": _round3(cheap_unit_sec),
                "n_units": len(units),
                "cosine_threshold": thr,
                "feature": "cheap_mfcc_flux_energy",
            },
            duration,
            dump,
        )

    # 1C change-point on cheap subwindows inside long units
    t_cheap_sw = time.perf_counter()
    subwins = island_subwindows(
        [isl for u in units for isl in u],
        CHEAP_WIN_SEC,
        CHEAP_STEP_SEC,
        min_embed,
    )
    cheap_sw_rows = []
    for s, e in subwins:
        sl = audio[int(s * sr) : int(e * sr)]
        cheap_sw_rows.append(cheap_vector(sl, sr))
    cheap_sw = _l2_normalize(np.stack(cheap_sw_rows)) if cheap_sw_rows else np.zeros((0, 1))
    cheap_sw_sec = time.perf_counter() - t_cheap_sw
    cheap_sw_adj = adjacent_cosines(cheap_sw)

    for thr in COSINE_CHEAP:
        # Split only inside long units; short units stay one segment.
        segs_cp: list[tuple[float, float]] = []
        labs_cp: list[int] = []
        next_id = 0
        for unit in units:
            speech_d = unit_speech_sec(unit)
            u_sub = island_subwindows(unit, CHEAP_WIN_SEC, CHEAP_STEP_SEC, min_embed)
            if speech_d < LONG_UNIT_SEC or len(u_sub) <= 1:
                segs_cp.append((round(unit_span(unit)[0], 3), round(unit_span(unit)[1], 3)))
                labs_cp.append(next_id)
                next_id += 1
                continue
            rows = []
            for s, e in u_sub:
                sl = audio[int(s * sr) : int(e * sr)]
                rows.append(cheap_vector(sl, sr))
            ux = _l2_normalize(np.stack(rows))
            adj = adjacent_cosines(ux)
            groups: list[list[int]] = [[0]]
            for i, sim in enumerate(adj):
                if sim >= thr:
                    groups[-1].append(i + 1)
                else:
                    groups.append([i + 1])
            for g in groups:
                segs_cp.append((round(u_sub[g[0]][0], 3), round(u_sub[g[-1]][1], 3)))
                labs_cp.append(next_id)
                next_id += 1
        t_cl = time.perf_counter()
        turns = labels_to_turns(segs_cp, labs_cp, diar_cfg, absorb=False)
        cluster_sec = time.perf_counter() - t_cl
        key = f"1C_cp_cos{thr:.2f}"
        out_methods[key] = method_row(
            clip_id,
            key,
            turns,
            {
                "stage": 1,
                "n_embed_calls": 0,
                "embed_sec": 0.0,
                "cluster_sec": _round3(cluster_sec),
                "cheap_feature_sec": _round3(cheap_sw_sec),
                "n_units": len(units),
                "n_subwindows": len(subwins),
                "n_segments_before_merge": len(segs_cp),
                "cosine_threshold": thr,
                "feature": "cheap_mfcc_flux_energy_changepoint",
            },
            duration,
            dump,
        )

    t_spec = time.perf_counter()
    spec_labels, spec_meta, spec_cluster = spectral_eigengap(cheap_sw, k_cap=K_CAP)
    spec_wall = time.perf_counter() - t_spec
    if spec_labels and subwins:
        turns = labels_to_turns(
            [(round(s, 3), round(e, 3)) for s, e in subwins],
            spec_labels,
            diar_cfg,
            absorb=False,
        )
    else:
        turns = []
    out_methods["1C_spec_cheap"] = method_row(
        clip_id,
        "1C_spec_cheap",
        turns,
        {
            "stage": 1,
            "n_embed_calls": 0,
            "embed_sec": 0.0,
            "cluster_sec": _round3(spec_cluster),
            "cheap_feature_sec": _round3(cheap_sw_sec),
            "n_subwindows": len(subwins),
            "spectral_meta": {k: spec_meta[k] for k in ("k", "n_windows", "k_cap", "eigengap_gaps") if k in spec_meta},
            "feature": "cheap_mfcc_flux_energy_spectral",
            "wall_sec": _round3(spec_wall),
        },
        duration,
        dump,
    )

    # --- Stage 2 from production-like islands ---
    segs_2a = []
    for isl in islands:
        segs_2a.extend(production_windows(isl, WINDOW_2A, STEP_2A, min_embed))
    embedder.reset()
    kept_2a, x_2a = embed_segments(audio, sr, segs_2a, embedder, min_embed)
    n_2a, sec_2a = embedder.n_calls, embedder.embed_sec
    lab_2a, meta_2a, cl_2a = cluster_ahc(x_2a, AHC_THRESHOLD)
    turns_2a = labels_to_turns(kept_2a, lab_2a, diar_cfg, absorb=True)
    out_methods["2A_overlap_1.5_0.75"] = method_row(
        clip_id,
        "2A_overlap_1.5_0.75",
        turns_2a,
        {
            "stage": 2,
            "n_embed_calls": n_2a,
            "embed_sec": _round3(sec_2a),
            "cluster_sec": _round3(cl_2a),
            "n_windows": len(kept_2a),
            "window_sec": WINDOW_2A,
            "step_sec": STEP_2A,
            "ahc_threshold": AHC_THRESHOLD,
            "cluster_meta": meta_2a,
        },
        duration,
        dump,
    )

    segs_2b = []
    for isl in islands:
        segs_2b.extend(nonoverlap_windows(isl, WINDOW_2B, min_embed))
    embedder.reset()
    kept_2b, x_2b = embed_segments(audio, sr, segs_2b, embedder, min_embed)
    n_2b, sec_2b = embedder.n_calls, embedder.embed_sec
    lab_2b, meta_2b, cl_2b = cluster_ahc(x_2b, AHC_THRESHOLD)
    turns_2b = labels_to_turns(kept_2b, lab_2b, diar_cfg, absorb=True)
    out_methods["2B_nooverlap_1.5"] = method_row(
        clip_id,
        "2B_nooverlap_1.5",
        turns_2b,
        {
            "stage": 2,
            "n_embed_calls": n_2b,
            "embed_sec": _round3(sec_2b),
            "cluster_sec": _round3(cl_2b),
            "n_windows": len(kept_2b),
            "window_sec": WINDOW_2B,
            "step_sec": WINDOW_2B,
            "ahc_threshold": AHC_THRESHOLD,
            "cluster_meta": meta_2b,
        },
        duration,
        dump,
    )

    # 2C AHC on unit WeSpeaker vectors (already computed)
    if len(x_units) == 0:
        lab_2c, meta_2c, cl_2c = [], {"n": 0}, 0.0
        full_2c: list[int] = [0] * len(units)
    else:
        lab_2c, meta_2c, cl_2c = cluster_ahc(x_units, AHC_THRESHOLD)
        mapped_2c: list[int | None] = [None] * len(units)
        for lab, i in zip(lab_2c, unit_ok_idx, strict=True):
            mapped_2c[i] = lab
        full_2c = fill_missing_labels(mapped_2c) if units else []
    segs_2c, labs_2c = island_segments_with_unit_labels(units, full_2c if full_2c else [0] * len(units))
    turns_2c = labels_to_turns(segs_2c, labs_2c, diar_cfg, absorb=True)
    out_methods["2C_unit_ahc0.85"] = method_row(
        clip_id,
        "2C_unit_ahc0.85",
        turns_2c,
        {
            "stage": 2,
            "n_embed_calls": n_unit_calls,
            "embed_sec": _round3(unit_embed_sec),
            "cluster_sec": _round3(cl_2c),
            "n_units": len(units),
            "n_units_embedded": n_unit_ok,
            "ahc_threshold": AHC_THRESHOLD,
            "cluster_meta": meta_2c,
            "unit_embed_wall_sec": _round3(unit_embed_wall),
        },
        duration,
        dump,
    )

    lab_2cs, meta_2cs, cl_2cs = spectral_eigengap(x_units, k_cap=K_CAP)
    mapped_s: list[int | None] = [None] * len(units)
    if unit_ok_idx and lab_2cs:
        for lab, i in zip(lab_2cs, unit_ok_idx, strict=True):
            mapped_s[i] = lab
    full_s = fill_missing_labels(mapped_s) if units else []
    segs_s, labs_s = island_segments_with_unit_labels(units, full_s if full_s else [0] * len(units))
    turns_s = labels_to_turns(segs_s, labs_s, diar_cfg, absorb=True)
    out_methods["2C_unit_spectral"] = method_row(
        clip_id,
        "2C_unit_spectral",
        turns_s,
        {
            "stage": 2,
            "n_embed_calls": n_unit_calls,
            "embed_sec": _round3(unit_embed_sec),
            "cluster_sec": _round3(cl_2cs),
            "n_units": len(units),
            "n_units_embedded": n_unit_ok,
            "spectral_meta": {k: meta_2cs[k] for k in ("k", "n_windows", "k_cap", "eigengap_gaps") if k in meta_2cs},
        },
        duration,
        dump,
    )

    return {
        "methods": out_methods,
        "unit_wespeaker_adjacent_cosine": sim_stats(unit_adj),
        "cheap_unit_adjacent_cosine": sim_stats(cheap_adj),
        "cheap_subwindow_adjacent_cosine": sim_stats(cheap_sw_adj),
        "timing_parts": {
            "n_embed_calls_unit": n_unit_calls,
            "embed_sec_unit": _round3(unit_embed_sec),
            "n_embed_calls_2a": n_2a,
            "embed_sec_2a": _round3(sec_2a),
            "n_windows_2a": len(kept_2a),
            "cluster_sec_2a": _round3(cl_2a),
            "n_embed_calls_2b": n_2b,
            "embed_sec_2b": _round3(sec_2b),
            "n_windows_2b": len(kept_2b),
            "cluster_sec_2b": _round3(cl_2b),
            "cluster_sec_2c_ahc": _round3(cl_2c),
            "cluster_sec_2c_spectral": _round3(cl_2cs),
            "n_units": len(units),
            "n_units_embedded": n_unit_ok,
            "cheap_unit_sec": _round3(cheap_unit_sec),
            "cheap_subwindow_sec": _round3(cheap_sw_sec),
            "n_cheap_subwindows": len(subwins),
        },
    }


def host_inventory() -> dict[str, Any]:
    def _run(cmd: list[str]) -> str:
        try:
            return subprocess.check_output(cmd, text=True, stderr=subprocess.STDOUT).strip()
        except (OSError, subprocess.CalledProcessError) as exc:
            return f"error: {exc}"

    cpu = ""
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    except OSError:
        cpu = ""
    py_ver = sys.version.split()[0]
    pkgs = {}
    for name in ("numpy", "scipy", "onnxruntime", "sklearn", "soundfile", "speakeronnx", "yaml"):
        try:
            mod = __import__(name if name != "sklearn" else "sklearn")
            pkgs[name] = getattr(mod, "__version__", "unknown")
        except Exception as exc:  # noqa: BLE001
            pkgs[name] = f"missing:{exc.__class__.__name__}"
    return {
        "nproc": os.cpu_count(),
        "cpu_model": cpu,
        "free_h": _run(["free", "-h"]),
        "df_h": _run(["df", "-h", "."]),
        "ffmpeg": _run(["ffmpeg", "-version"]).splitlines()[0] if _run(["ffmpeg", "-version"]) else None,
        "python": py_ver,
        "onnx_threads": ONNX_THREADS,
        "packages": pkgs,
        "hf_token": "present" if os.environ.get("HF_TOKEN") else "absent",
    }


def jsonable(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items() if k not in {"regions", "islands", "unit_lists"}}
    if isinstance(obj, list):
        return [jsonable(v) for v in obj]
    if isinstance(obj, (np.floating, np.integer)):
        return obj.item()
    if isinstance(obj, Interval):
        return {"start": _round3(obj.start), "end": _round3(obj.end)}
    return obj


def main() -> None:
    t_all = time.perf_counter()
    rss = RssSampler()
    rss.start()
    OUT.mkdir(parents=True, exist_ok=True)
    TIMELINES.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    vad_cfg, diar_cfg = load_vad_diar_cfg()
    print(
        f"config vad_premerge_gap_sec={diar_cfg.merge.vad_premerge_gap_sec} "
        f"min_embed={diar_cfg.embed.min_sec} glue={GLUE_SEC} onnx_threads={ONNX_THREADS}",
        flush=True,
    )

    t_load = time.perf_counter()
    raw = SpeakerEmbedder(model="wespeaker-resnet34")
    model_load_sec = time.perf_counter() - t_load
    print(f"model_load_sec={model_load_sec:.3f}", flush=True)
    embedder = CountingEmbedder(raw)
    vad = SileroVadDetector()

    quality: dict[str, Any] = {}
    preprocess: dict[str, Any] = {}
    adjacent: dict[str, Any] = {}

    all_clips = list(QUALITY_CLIPS) + [TIMING_CLIP]
    timing_5min: dict[str, Any] = {}

    for clip_id, src in all_clips:
        print(f"== {clip_id} ==", flush=True)
        wav = copy_clip(clip_id, src)
        audio, sr = sf.read(str(wav), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        duration = float(len(audio) / sr)
        prep = preprocess_clip(wav, vad, vad_cfg, diar_cfg)
        preprocess[clip_id] = {k: v for k, v in prep.items() if k not in {"regions", "islands", "unit_lists"}}
        print(
            f"  regions={prep['n_regions']} islands={prep['n_islands']} "
            f"units={prep['n_units']} speech={prep['speech_sec']}s vad={prep['vad_sec']}s",
            flush=True,
        )
        dump = clip_id != "timing_5min"
        ran = run_methods_for_clip(
            clip_id, wav, audio, sr, duration, prep, embedder, diar_cfg, dump=dump
        )
        if dump:
            quality[clip_id] = ran["methods"]
            adjacent[clip_id] = {
                "unit_wespeaker_adjacent_cosine": ran["unit_wespeaker_adjacent_cosine"],
                "cheap_unit_adjacent_cosine": ran["cheap_unit_adjacent_cosine"],
                "cheap_subwindow_adjacent_cosine": ran["cheap_subwindow_adjacent_cosine"],
            }
        parts = ran["timing_parts"]
        print(
            f"  2A n_embed={parts['n_embed_calls_2a']} embed_sec={parts['embed_sec_2a']} "
            f"2B n_embed={parts['n_embed_calls_2b']} 2C n_embed={parts['n_embed_calls_unit']}",
            flush=True,
        )
        if clip_id == "timing_5min":
            timing_5min = {
                "clip": clip_id,
                "duration_sec": _round3(duration),
                "model_load_sec": _round3(model_load_sec),
                "vad_sec": prep["vad_sec"],
                "n_regions": prep["n_regions"],
                "n_islands": prep["n_islands"],
                "n_units": prep["n_units"],
                "n_islands_lt_1s": prep["n_islands_lt_1s"],
                "speech_sec": prep["speech_sec"],
                "island_duration_hist": prep["island_duration_hist"],
                "unit_speech_hist": prep["unit_speech_hist"],
                "methods": {
                    "1A": {
                        "n_embed_calls": parts["n_embed_calls_unit"],
                        "embed_sec": parts["embed_sec_unit"],
                        "n_units": parts["n_units"],
                        "n_units_embedded": parts["n_units_embedded"],
                        "cluster_sec": 0.0,
                        "note": "adjacent cosine on unit embeds; cluster_sec negligible vs embed",
                    },
                    "1B": {
                        "n_embed_calls": 0,
                        "embed_sec": 0.0,
                        "cheap_feature_sec": parts["cheap_unit_sec"],
                        "n_units": parts["n_units"],
                    },
                    "1C": {
                        "n_embed_calls": 0,
                        "embed_sec": 0.0,
                        "cheap_feature_sec": parts["cheap_subwindow_sec"],
                        "n_subwindows": parts["n_cheap_subwindows"],
                    },
                    "2A_overlap_1.5_0.75": {
                        "n_embed_calls": parts["n_embed_calls_2a"],
                        "embed_sec": parts["embed_sec_2a"],
                        "cluster_sec": parts["cluster_sec_2a"],
                        "n_windows": parts["n_windows_2a"],
                        "ms_per_embed": _round1(1000.0 * parts["embed_sec_2a"] / max(parts["n_embed_calls_2a"], 1)),
                    },
                    "2B_nooverlap_1.5": {
                        "n_embed_calls": parts["n_embed_calls_2b"],
                        "embed_sec": parts["embed_sec_2b"],
                        "cluster_sec": parts["cluster_sec_2b"],
                        "n_windows": parts["n_windows_2b"],
                        "ms_per_embed": _round1(1000.0 * parts["embed_sec_2b"] / max(parts["n_embed_calls_2b"], 1)),
                    },
                    "2C_one_embed_per_unit": {
                        "n_embed_calls": parts["n_embed_calls_unit"],
                        "embed_sec": parts["embed_sec_unit"],
                        "cluster_sec_ahc": parts["cluster_sec_2c_ahc"],
                        "cluster_sec_spectral": parts["cluster_sec_2c_spectral"],
                        "n_units": parts["n_units"],
                        "n_units_embedded": parts["n_units_embedded"],
                        "ms_per_embed": _round1(1000.0 * parts["embed_sec_unit"] / max(parts["n_embed_calls_unit"], 1)),
                    },
                },
                "hypothesis": {
                    "expected": "2C n_embed_calls << 2A; 2B between 2A and 2C",
                    "n_embed_2a": parts["n_embed_calls_2a"],
                    "n_embed_2b": parts["n_embed_calls_2b"],
                    "n_embed_2c": parts["n_embed_calls_unit"],
                    "holds_2c_lt_2a": parts["n_embed_calls_unit"] < parts["n_embed_calls_2a"],
                    "holds_2b_between": (
                        parts["n_embed_calls_unit"] < parts["n_embed_calls_2b"] < parts["n_embed_calls_2a"]
                    ),
                },
            }

    peak_kb = rss.stop()
    wall = time.perf_counter() - t_all
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True
    ).strip()

    results = {
        "schema_version": "1",
        "task": "D5.diar-twopass",
        "branch": branch,
        "commit_at_run_start": commit,
        "model_load_sec": _round3(model_load_sec),
        "glue_sec": GLUE_SEC,
        "vad_premerge_gap_sec": diar_cfg.merge.vad_premerge_gap_sec,
        "ahc_threshold": AHC_THRESHOLD,
        "cosine_1a": list(COSINE_1A),
        "cosine_cheap": list(COSINE_CHEAP),
        "long_unit_sec": LONG_UNIT_SEC,
        "cheap_window_sec": CHEAP_WIN_SEC,
        "note": (
            "1B/1C use cheap MFCC+flux+energy features, not WeSpeaker. "
            "Stage 2 starts from production-like VAD islands (premerge 0.5 s); "
            "2C clusters glued units (<1 s). Stage 1 turns are not absorb-merged; "
            "stage 2 uses production absorb 1.0 s / same-speaker gap 0.3 s. "
            "No gold. Crumb counts are log-only."
        ),
        "preprocess": jsonable(preprocess),
        "adjacent": adjacent,
        "quality": jsonable(quality),
        "timing_5min": timing_5min,
        "wall_sec": _round3(wall),
        "peak_rss_mb": _round1(peak_kb / 1024.0),
    }
    (OUT / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    meta = {
        "branch": branch,
        "commit": commit,
        "task": "D5.diar-twopass",
        "host": host_inventory(),
        "model_load_sec": _round3(model_load_sec),
        "wall_sec": _round3(wall),
        "peak_rss_mb": _round1(peak_kb / 1024.0),
        "llm_calls": 0,
        "onnx_threads": ONNX_THREADS,
        "timing_5min_n_embed": {
            "2A": timing_5min.get("methods", {}).get("2A_overlap_1.5_0.75", {}).get("n_embed_calls"),
            "2B": timing_5min.get("methods", {}).get("2B_nooverlap_1.5", {}).get("n_embed_calls"),
            "2C": timing_5min.get("methods", {}).get("2C_one_embed_per_unit", {}).get("n_embed_calls"),
        },
    }
    (OUT / "run_meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"done wall_sec={wall:.1f} peak_rss_mb={peak_kb/1024:.1f}", flush=True)
    print(f"timing_5min={json.dumps(timing_5min.get('methods', {}), sort_keys=True)}", flush=True)


if __name__ == "__main__":
    main()

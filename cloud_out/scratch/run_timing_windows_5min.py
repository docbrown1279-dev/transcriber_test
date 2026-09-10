#!/usr/bin/env python3
"""Timing-only: WeSpeaker window 1.5/0.75 vs 3.0/1.5 on timing_5min.wav.

Same Silero VAD mask. No quality grid, no M0/M1/M2 re-run, no eval/gold.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import onnxruntime as ort
import soundfile as sf
import yaml
from sklearn.cluster import AgglomerativeClustering

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

ONNX_THREADS = 2
os.environ.setdefault("OMP_NUM_THREADS", str(ONNX_THREADS))
os.environ.setdefault("MKL_NUM_THREADS", str(ONNX_THREADS))
os.environ.setdefault("OPENBLAS_NUM_THREADS", str(ONNX_THREADS))
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
from transcriber.diarization.regions import Interval, merge_speech_regions  # noqa: E402
from transcriber.diarization.wespeaker import _l2_normalize  # noqa: E402
from transcriber.vad.silero import SileroVadDetector  # noqa: E402

INPUTS = ROOT / "cloud_in" / "inputs"
OUT = ROOT / "cloud_out"
WORK = Path("/tmp/d5-diar-spectral")
WAV_SRC = INPUTS / "clips" / "timing_5min.wav"
PRIOR_RESULTS = OUT / "results.json"

PRESETS: list[tuple[str, float, float]] = [
    ("baseline", 1.5, 0.75),
    ("coarse", 3.0, 1.5),
]
CLUSTER_THRESHOLD = 0.85


def _round3(value: float) -> float:
    return round(float(value), 3)


def _round1(value: float) -> float:
    return round(float(value), 1)


def load_vad_diar_cfg() -> tuple[VadConfig, DiarizationConfig]:
    base = yaml.safe_load((ROOT / "config" / "base.yaml").read_text(encoding="utf-8"))
    demo = yaml.safe_load((ROOT / "config" / "profiles" / "demo.yaml").read_text(encoding="utf-8"))
    merged = deep_merge(base, demo)
    return (
        VadConfig.model_validate(merged["vad"]),
        DiarizationConfig.model_validate(merged["diarization"]),
    )


def window_embeddings(
    audio: np.ndarray,
    sr: int,
    speech_islands: list[Interval],
    embedder: SpeakerEmbedder,
    window_sec: float,
    step_sec: float,
    min_embed: float,
) -> tuple[int, np.ndarray, float]:
    """Same windowing as WeSpeakerDiarizer.diarize."""
    embeddings: list[np.ndarray] = []
    n_windows = 0
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
            embeddings.append(np.asarray(emb, dtype=np.float64))
            n_windows += 1
            continue
        win_len = int(window_sec * sr)
        step_len = int(step_sec * sr)
        curr = r_start_idx
        while curr + win_len <= r_end_idx:
            emb = embedder.embed(audio[curr : curr + win_len])
            embeddings.append(np.asarray(emb, dtype=np.float64))
            n_windows += 1
            curr += step_len
        rem = r_end_idx - curr
        if rem >= int(min_embed * sr):
            emb = embedder.embed(audio[curr:r_end_idx])
            embeddings.append(np.asarray(emb, dtype=np.float64))
            n_windows += 1
    embed_wall = time.perf_counter() - t0
    if not embeddings:
        empty = np.zeros((0, 1), dtype=np.float64)
        return n_windows, empty, embed_wall
    x = _l2_normalize(np.stack(embeddings))
    return n_windows, x, embed_wall


def cluster_ahc_ms(x: np.ndarray, threshold: float) -> float:
    if len(x) <= 1:
        return 0.0
    t0 = time.perf_counter()
    AgglomerativeClustering(
        metric="cosine",
        linkage="average",
        distance_threshold=threshold,
        n_clusters=None,
    ).fit(x)
    return (time.perf_counter() - t0) * 1000.0


def ms_per_window(embed_sec: float, n_windows: int) -> float:
    if n_windows <= 0:
        return 0.0
    return _round1((embed_sec * 1000.0) / n_windows)


def main() -> None:
    if not WAV_SRC.is_file():
        raise FileNotFoundError(f"Packed wav missing: {WAV_SRC}")

    prior: dict[str, Any] = {}
    if PRIOR_RESULTS.is_file():
        packed = json.loads(PRIOR_RESULTS.read_text(encoding="utf-8"))
        t5 = packed.get("timing_5min", {})
        prior = {
            "n_windows": t5.get("pass1", {}).get("n_windows"),
            "pass1_embed_sec": t5.get("pass1", {}).get("embed_sec"),
            "pass2_embed_sec": t5.get("pass2", {}).get("embed_sec"),
            "window_sec": packed.get("window_sec"),
            "step_sec": packed.get("step_sec"),
            "source": "cloud_out/results.json",
        }

    vad_cfg, diar_cfg = load_vad_diar_cfg()
    min_embed = diar_cfg.embed.min_sec
    premerge = diar_cfg.merge.vad_premerge_gap_sec

    WORK.mkdir(parents=True, exist_ok=True)
    dest_dir = WORK / "timing_5min_windows"
    dest_dir.mkdir(parents=True, exist_ok=True)
    wav = dest_dir / "audio.wav"
    if not wav.is_file() or wav.stat().st_size != WAV_SRC.stat().st_size:
        shutil.copy2(WAV_SRC, wav)

    print("VAD timing_5min…", flush=True)
    detector = SileroVadDetector()
    speech = detector.detect(wav, vad_cfg, job_id="timing_5min_windows")
    audio, sr = sf.read(str(wav))
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    duration = _round3(float(len(audio) / sr))
    islands = merge_speech_regions(
        [Interval(start=r.start, end=r.end) for r in speech.regions],
        max_gap_sec=premerge,
        min_duration_sec=min_embed,
    )
    vad_row = {
        "duration_sec": duration,
        "n_regions": len(speech.regions),
        "n_islands": len(islands),
        "speech_sec": speech.speech_sec,
        "vad_runtime_sec": speech.runtime_sec,
        "vad_premerge_gap_sec": premerge,
        "min_embed_sec": min_embed,
    }

    print("Loading WeSpeaker embedder…", flush=True)
    t_load = time.perf_counter()
    embedder = SpeakerEmbedder(model="wespeaker-resnet34")
    model_load_sec = _round3(time.perf_counter() - t_load)
    print(f"model_load_sec={model_load_sec}", flush=True)

    presets_out: dict[str, Any] = {}
    for name, window_sec, step_sec in PRESETS:
        print(f"embed {name} {window_sec}/{step_sec} pass1…", flush=True)
        n1, x1, e1 = window_embeddings(
            audio, sr, islands, embedder, window_sec, step_sec, min_embed
        )
        c1_ms = _round1(cluster_ahc_ms(x1, CLUSTER_THRESHOLD))
        print(f"embed {name} pass2…", flush=True)
        n2, x2, e2 = window_embeddings(
            audio, sr, islands, embedder, window_sec, step_sec, min_embed
        )
        c2_ms = _round1(cluster_ahc_ms(x2, CLUSTER_THRESHOLD))
        if n1 != n2:
            raise RuntimeError(f"{name}: n_windows pass1={n1} pass2={n2}")
        presets_out[name] = {
            "window_sec": window_sec,
            "step_sec": step_sec,
            "n_windows": int(n1),
            "pass1": {
                "embed_sec": _round3(e1),
                "ms_per_window": ms_per_window(e1, n1),
                "cluster_ahc_0.85_ms": c1_ms,
            },
            "pass2": {
                "embed_sec": _round3(e2),
                "ms_per_window": ms_per_window(e2, n2),
                "cluster_ahc_0.85_ms": c2_ms,
            },
        }
        print(
            f"  n_windows={n1} embed1={_round3(e1)}s embed2={_round3(e2)}s "
            f"ms/win={ms_per_window(e1, n1)}/{ms_per_window(e2, n2)} "
            f"cluster_ms={c1_ms}/{c2_ms}",
            flush=True,
        )

    payload = {
        "schema_version": "1",
        "experiment": "D5.diar-spectral.timing_windows_5min",
        "clip": "cloud_in/inputs/clips/timing_5min.wav",
        "model": "wespeaker-resnet34",
        "onnx_threads": ONNX_THREADS,
        "affinity": "taskset -c 0,1",
        "model_load_sec": model_load_sec,
        "same_vad_mask": True,
        "cluster": {
            "method": "AgglomerativeClustering cosine average",
            "distance_threshold": CLUSTER_THRESHOLD,
            "note": "optional cluster ms only; not a quality re-run",
        },
        "vad": vad_row,
        "prior_results_json_baseline_1.5_0.75": prior,
        "presets": presets_out,
    }
    out_json = OUT / "timing_windows_5min.json"
    out_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {out_json}", flush=True)


if __name__ == "__main__":
    main()

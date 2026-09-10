#!/usr/bin/env python3
"""Throwaway D5.TTFT-diar research runner (not production pipeline).

Loads packed wavs, runs Silero VAD once per clip, then WeSpeaker window
presets + cluster-threshold grid. Writes cloud_out/results.json and timelines.
Does not read eval/, .env, or data/. Does not call ASR/LLM.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
import yaml
from sklearn.cluster import AgglomerativeClustering

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

os.environ.setdefault("OMP_NUM_THREADS", "2")
os.environ.setdefault("MKL_NUM_THREADS", "2")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "2")
os.environ.setdefault("NUMEXPR_NUM_THREADS", "2")

from speakeronnx import SpeakerEmbedder  # noqa: E402

from transcriber.config.loader import deep_merge  # noqa: E402
from transcriber.config.schema import DiarizationConfig, VadConfig  # noqa: E402
from transcriber.diarization.merge import merge_turns  # noqa: E402
from transcriber.diarization.regions import Interval, merge_speech_regions  # noqa: E402
from transcriber.diarization.wespeaker import (  # noqa: E402
    _l2_normalize,
    _renumber_speakers,
)
from transcriber.models.artifacts import TurnItem  # noqa: E402
from transcriber.vad.silero import SileroVadDetector  # noqa: E402

INPUTS = ROOT / "cloud_in" / "inputs"
OUT = ROOT / "cloud_out"
WORK = Path("/tmp/d5-ttft-diar")
TIMELINES = OUT / "timelines"

WINDOW_PRESETS: dict[str, tuple[float, float]] = {
    "baseline": (1.5, 0.75),
    "A": (2.0, 1.0),
    "B": (3.0, 1.5),
}
THRESHOLDS = (0.80, 0.82, 0.85, 0.88)
CRUMB_SPEECH_SEC = 2.5
SUBSTANTIAL_SPEECH_SEC = 3.0
S1_THRESHOLD = 0.85

CLIPS: list[tuple[str, Path]] = [
    ("clip01_embeddings_men", INPUTS / "clips" / "clip01_embeddings_men.wav"),
    ("clip02_vadim_q", INPUTS / "clips" / "clip02_vadim_q.wav"),
    ("clip03_woman_men", INPUTS / "clips" / "clip03_woman_men.wav"),
    ("test_apartments", INPUTS / "regression" / "test_apartments.wav"),
    ("test_ninth", INPUTS / "regression" / "test_ninth.wav"),
]


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


def cluster_labels(
    x: np.ndarray, threshold: float
) -> tuple[list[int], float, dict[str, Any]]:
    if len(x) == 0:
        return [], 0.0, {"n_windows": 0, "knee_gap": None, "n_merges": 0}
    t0 = time.perf_counter()
    if len(x) == 1:
        labels = [0]
        knee: dict[str, Any] = {"n_windows": 1, "knee_gap": None, "n_merges": 0}
    else:
        clusterer = AgglomerativeClustering(
            metric="cosine",
            linkage="average",
            distance_threshold=threshold,
            n_clusters=None,
            compute_distances=True,
        )
        labels = [int(v) for v in clusterer.fit_predict(x).tolist()]
        distances = np.asarray(getattr(clusterer, "distances_", []), dtype=np.float64)
        if distances.size >= 2:
            gaps = np.diff(distances)
            knee = {
                "n_windows": int(len(x)),
                "n_merges": int(distances.size),
                "knee_gap": _round3(float(np.max(gaps))),
                "knee_merge_distance": _round3(float(distances[int(np.argmax(gaps)) + 1])),
                "min_merge_distance": _round3(float(np.min(distances))),
                "max_merge_distance": _round3(float(np.max(distances))),
            }
        else:
            knee = {
                "n_windows": int(len(x)),
                "n_merges": int(distances.size),
                "knee_gap": None,
            }
    cluster_wall = time.perf_counter() - t0
    return labels, cluster_wall, knee


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
    crumbs = {k: v for k, v in speech.items() if v < 3.0}
    crumbs_25 = {k: v for k, v in speech.items() if v <= CRUMB_SPEECH_SEC}
    substantial = {k: v for k, v in speech.items() if v >= SUBSTANTIAL_SPEECH_SEC}
    top1_id = max(speech, key=speech.get) if speech else None
    top1 = speech[top1_id] if top1_id else 0.0
    n_sub = len(substantial)
    if n_sub == 1:
        soft = "undersplit"
    elif n_sub >= 10:
        soft = "oversplit"
    elif 2 <= n_sub <= 4:
        soft = "healthy"
    elif n_sub == 0:
        soft = "no_substantial"
    else:
        soft = "outside_band"
    return {
        "speaker_count": len(speech),
        "substantial_count": n_sub,
        "crumb_count_lt3s": len(crumbs),
        "crumb_count_le2_5s": len(crumbs_25),
        "speech_sec_per_id": speech,
        "top1_id": top1_id,
        "top1_speech_sec": _round3(top1),
        "top1_share": _round3(top1 / total),
        "total_turn_speech_sec": _round3(sum(speech.values())),
        "soft_bar": soft,
    }


def _crumb_pass_centroid(
    x: np.ndarray,
    labels: list[int],
    segments: list[tuple[float, float]],
    cfg: DiarizationConfig,
) -> tuple[list[int], dict[str, Any]]:
    """One pass: reassign window labels whose merged speech <= 2.5s."""
    raw_speech: dict[int, float] = defaultdict(float)
    tmp = [
        {"start": s, "end": e, "speaker": f"SPEAKER_{int(lbl):02d}"}
        for (s, e), lbl in zip(segments, labels, strict=True)
    ]
    raw_merged = merge_turns(
        tmp,
        same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
        absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
    )
    clipped: list[TurnItem] = list(raw_merged)
    for i in range(len(clipped) - 1):
        if clipped[i].end > clipped[i + 1].start:
            new_boundary = round(clipped[i + 1].start, 3)
            if new_boundary > clipped[i].start:
                clipped[i] = TurnItem(
                    id=clipped[i].id,
                    start=clipped[i].start,
                    end=new_boundary,
                    speaker=clipped[i].speaker,
                )
    for turn in clipped:
        raw_speech[int(turn.speaker.split("_")[1])] += turn.end - turn.start

    crumb_lbls = {lbl for lbl, sec in raw_speech.items() if sec <= CRUMB_SPEECH_SEC}
    large_lbls = {lbl for lbl, sec in raw_speech.items() if sec > CRUMB_SPEECH_SEC}
    if not crumb_lbls or not large_lbls:
        return list(labels), {
            "merged_crumbs": sorted(f"SPEAKER_{i:02d}" for i in crumb_lbls),
            "n_windows_reassigned": 0,
            "skipped": True,
        }

    centroids: dict[int, np.ndarray] = {}
    for lbl in set(labels):
        rows = x[[i for i, lab in enumerate(labels) if lab == lbl]]
        vec = rows.mean(axis=0)
        nrm = np.linalg.norm(vec)
        centroids[lbl] = vec / max(nrm, 1e-12)

    new_labels = list(labels)
    n_reassigned = 0
    for i, lbl in enumerate(labels):
        if lbl not in crumb_lbls:
            continue
        c = centroids[lbl]
        best = min(large_lbls, key=lambda L: float(1.0 - np.dot(c, centroids[L])))
        new_labels[i] = best
        n_reassigned += 1
    return new_labels, {
        "merged_crumbs": sorted(f"SPEAKER_{i:02d}" for i in crumb_lbls),
        "n_windows_reassigned": n_reassigned,
        "skipped": False,
    }


def crumb_merge_centroid(
    x: np.ndarray,
    labels: list[int],
    segments: list[tuple[float, float]],
    cfg: DiarizationConfig,
    max_passes: int = 4,
) -> tuple[list[TurnItem], dict[str, Any]]:
    """Reassign speakers with speech <= 2.5s to nearest large centroid (cosine)."""
    turns = labels_to_turns(segments, labels, cfg)
    if not turns:
        return turns, {"merged_crumbs": [], "method": "centroid_cosine", "passes": 0}
    cur = list(labels)
    passes: list[dict[str, Any]] = []
    skipped = True
    for _ in range(max_passes):
        cur, meta = _crumb_pass_centroid(x, cur, segments, cfg)
        passes.append(meta)
        if meta.get("skipped"):
            break
        skipped = False
    merged_turns = labels_to_turns(segments, cur, cfg)
    crumbs = [spk for spk, sec in speaker_speech(merged_turns).items() if sec <= CRUMB_SPEECH_SEC]
    return merged_turns, {
        "method": "centroid_cosine",
        "merged_crumbs": crumbs,
        "passes": passes,
        "n_passes": len(passes),
        "skipped": skipped,
    }


def crumb_merge_time_neighbor(
    labels: list[int],
    segments: list[tuple[float, float]],
    cfg: DiarizationConfig,
) -> tuple[list[TurnItem], dict[str, Any]]:
    """Absorb crumb turns into nearest large neighbor by time gap."""
    turns = labels_to_turns(segments, labels, cfg)
    speech = speaker_speech(turns)
    large = {spk for spk, sec in speech.items() if sec > CRUMB_SPEECH_SEC}
    crumbs = [spk for spk, sec in speech.items() if sec <= CRUMB_SPEECH_SEC]
    if not crumbs or not large or len(turns) <= 1:
        return turns, {
            "method": "time_neighbor",
            "merged_crumbs": crumbs,
            "skipped": True,
        }
    mutable = [
        {"start": t.start, "end": t.end, "speaker": t.speaker, "id": t.id} for t in turns
    ]
    reassigned = 0
    for row in mutable:
        if row["speaker"] not in crumbs:
            continue
        best_spk = None
        best_gap = 1e9
        for other in mutable:
            if other["speaker"] not in large:
                continue
            if other["end"] <= row["start"]:
                gap = row["start"] - other["end"]
            elif other["start"] >= row["end"]:
                gap = other["start"] - row["end"]
            else:
                gap = 0.0
            if gap < best_gap:
                best_gap = gap
                best_spk = other["speaker"]
        if best_spk is not None:
            row["speaker"] = best_spk
            reassigned += 1
    merged = merge_turns(
        mutable,
        same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
        absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
    )
    merged = _renumber_speakers(merged)
    return merged, {
        "method": "time_neighbor",
        "merged_crumbs": crumbs,
        "n_turns_reassigned": reassigned,
        "skipped": False,
    }


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


def main() -> None:
    t_all = time.perf_counter()
    rss = RssSampler()
    rss.start()
    OUT.mkdir(parents=True, exist_ok=True)
    TIMELINES.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)

    vad_cfg, diar_cfg = load_vad_diar_cfg()
    min_embed = diar_cfg.embed.min_sec
    premerge = diar_cfg.merge.vad_premerge_gap_sec

    detector = SileroVadDetector()
    print("Loading WeSpeaker embedder (wespeaker-resnet34)…", flush=True)
    t_load = time.perf_counter()
    embedder = SpeakerEmbedder(model="wespeaker-resnet34")
    # One dummy frame so first-clip embed_wall is not dominated by session init.
    dummy = np.zeros(int(16000 * 0.5), dtype=np.float32)
    embedder.embed(dummy)
    model_load_sec = _round3(time.perf_counter() - t_load)
    print(f"model_load_sec={model_load_sec}", flush=True)

    vad_rows: dict[str, Any] = {}
    audio_cache: dict[str, tuple[np.ndarray, int, list[Interval], float]] = {}

    for clip_id, src in CLIPS:
        if not src.is_file():
            raise FileNotFoundError(f"Packed wav missing: {src}")
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

    embed_cache: dict[tuple[str, str], dict[str, Any]] = {}
    grid: list[dict[str, Any]] = []
    crumb_rows: list[dict[str, Any]] = []

    for clip_id, _src in CLIPS:
        audio, sr, islands, duration = audio_cache[clip_id]
        for preset, (window_sec, step_sec) in WINDOW_PRESETS.items():
            print(f"embed {clip_id} {preset} window={window_sec} step={step_sec}…", flush=True)
            segments, x, embed_wall = window_embeddings(
                audio, sr, islands, embedder, window_sec, step_sec, min_embed
            )
            embed_cache[(clip_id, preset)] = {
                "segments": segments,
                "x": x,
                "embed_wall_sec": _round3(embed_wall),
                "n_windows": int(len(segments)),
                "window_sec": window_sec,
                "step_sec": step_sec,
            }
            for threshold in THRESHOLDS:
                labels, cluster_wall, knee = cluster_labels(x, threshold)
                turns = labels_to_turns(segments, labels, diar_cfg)
                stats = summarize_turns(turns)
                row = {
                    "clip": clip_id,
                    "preset": preset,
                    "window_sec": window_sec,
                    "step_sec": step_sec,
                    "cluster_distance_threshold": threshold,
                    "n_windows": int(len(segments)),
                    "embed_wall_sec": _round3(embed_wall),
                    "cluster_wall_sec": _round3(cluster_wall),
                    "duration_sec": duration,
                    "knee": knee,
                    **stats,
                }
                grid.append(row)
                dump_timeline(
                    TIMELINES / f"{clip_id}__{preset}__thr{threshold:.2f}.json",
                    turns,
                    {
                        "clip": clip_id,
                        "preset": preset,
                        "cluster_distance_threshold": threshold,
                        "n_windows": int(len(segments)),
                    },
                )
                # Crumb prototype on every cell; tables highlight S1 0.85 + tuner window.
                c_turns, c_meta = crumb_merge_centroid(x, labels, segments, diar_cfg)
                t_turns, t_meta = crumb_merge_time_neighbor(labels, segments, diar_cfg)
                crumb_rows.append(
                    {
                        "clip": clip_id,
                        "preset": preset,
                        "cluster_distance_threshold": threshold,
                        "before": {
                            "speaker_count": stats["speaker_count"],
                            "substantial_count": stats["substantial_count"],
                            "crumb_count_le2_5s": stats["crumb_count_le2_5s"],
                            "top1_share": stats["top1_share"],
                            "soft_bar": stats["soft_bar"],
                        },
                        "after_centroid": {
                            **summarize_turns(c_turns),
                            "meta": c_meta,
                        },
                        "after_time_neighbor": {
                            **summarize_turns(t_turns),
                            "meta": t_meta,
                        },
                    }
                )
                dump_timeline(
                    TIMELINES / f"{clip_id}__{preset}__thr{threshold:.2f}__crumb_centroid.json",
                    c_turns,
                    {
                        "clip": clip_id,
                        "preset": preset,
                        "cluster_distance_threshold": threshold,
                        "variant": "crumb_centroid",
                    },
                )

    peak_kb = rss.stop()
    wall_sec = _round3(time.perf_counter() - t_all)
    results = {
        "schema_version": "1",
        "experiment": "D5.TTFT-diar",
        "model": "wespeaker-resnet34",
        "model_load_sec": model_load_sec,
        "onnx_threads_target": 2,
        "merge": {
            "same_speaker_gap_sec": diar_cfg.merge.same_speaker_gap_sec,
            "absorb_turn_shorter_than_sec": diar_cfg.merge.absorb_turn_shorter_than_sec,
            "vad_premerge_gap_sec": diar_cfg.merge.vad_premerge_gap_sec,
            "min_embed_sec": min_embed,
        },
        "constants": {
            "crumb_speech_sec": CRUMB_SPEECH_SEC,
            "substantial_speech_sec": SUBSTANTIAL_SPEECH_SEC,
            "s1_threshold": S1_THRESHOLD,
            "window_presets": {
                name: {"window_sec": w, "step_sec": s} for name, (w, s) in WINDOW_PRESETS.items()
            },
            "thresholds": list(THRESHOLDS),
        },
        "vad": vad_rows,
        "grid": grid,
        "crumb": crumb_rows,
        "wall_sec": wall_sec,
        "peak_rss_mb": _round3(peak_kb / 1024.0),
    }
    (OUT / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {OUT / 'results.json'} wall_sec={wall_sec} peak_rss_mb={results['peak_rss_mb']}")


if __name__ == "__main__":
    main()

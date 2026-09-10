#!/usr/bin/env python3
"""Follow-up: tune 2C unit-AHC / sequential centroids / long-loud anchors.

Reuses Silero islands + glue <1 s units and one WeSpeaker embed per unit.
Does not redo cheap 1B/1C, does not redo 3.0/1.5 windows, does not redo AHC 0.85.
No eval/gold, no production src/config edits.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
SCRATCH = Path(__file__).resolve().parent
if str(SCRATCH) not in sys.path:
    sys.path.insert(0, str(SCRATCH))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import run_d5_diar_twopass as base  # noqa: E402

from speakeronnx import SpeakerEmbedder  # noqa: E402

from transcriber.diarization.wespeaker import _l2_normalize  # noqa: E402

T1_AHC = (0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80)
T2_THR = (0.40, 0.55, 0.70)
T3_THR = (0.40, 0.55, 0.70)
ANCHOR_MIN_SEC = 3.0
ENERGY_PCTL = 75.0
PRIOR_2A = {
    "n_embed_calls": 366,
    "embed_sec": 5.940,
    "n_windows": 366,
}
PRIOR_2C = {
    "n_embed_calls": 21,
    "embed_sec": 3.033,
    "n_units": 21,
    "ahc": 0.85,
}


def sequential_nearest_centroid(x: np.ndarray, thr: float) -> tuple[list[int], dict[str, Any], float]:
    """Walk units in time; merge to nearest existing centroid or spawn a new one."""
    t0 = time.perf_counter()
    n = len(x)
    if n == 0:
        return [], {"n": 0, "threshold": thr, "n_new": 0}, 0.0
    labels = [0]
    centroids = [np.asarray(x[0], dtype=np.float64).copy()]
    counts = [1]
    n_new = 1
    for i in range(1, n):
        vec = np.asarray(x[i], dtype=np.float64)
        sims = [float(np.dot(vec, c)) for c in centroids]
        best = int(np.argmax(sims))
        if sims[best] >= thr:
            labels.append(best)
            counts[best] += 1
            acc = centroids[best] * (counts[best] - 1) + vec
            centroids[best] = _l2_normalize(acc.reshape(1, -1))[0]
        else:
            labels.append(len(centroids))
            centroids.append(vec.copy())
            counts.append(1)
            n_new += 1
    wall = time.perf_counter() - t0
    return labels, {"n": n, "threshold": thr, "n_new": n_new, "n_labels": len(set(labels))}, wall


def unit_rms(audio: np.ndarray, sr: int, unit: list[Any]) -> float:
    sl = base.concat_unit_audio(audio, sr, unit)
    if sl.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.asarray(sl, dtype=np.float64) ** 2)))


def select_anchors(
    units: list[list[Any]],
    audio: np.ndarray,
    sr: int,
    min_sec: float = ANCHOR_MIN_SEC,
    energy_pctl: float = ENERGY_PCTL,
) -> tuple[list[int], dict[str, Any]]:
    """Long (speech ≥ min_sec) OR loud (RMS ≥ energy percentile). Not neighbor-cosine."""
    n = len(units)
    if n == 0:
        return [], {"n_units": 0, "n_anchors": 0, "n_long": 0, "n_loud": 0}
    speech = [base.unit_speech_sec(u) for u in units]
    rms = [unit_rms(audio, sr, u) for u in units]
    long_idx = {i for i, d in enumerate(speech) if d >= min_sec}
    if not long_idx:
        long_idx.add(int(np.argmax(speech)))
    pctl = float(np.percentile(np.asarray(rms, dtype=np.float64), energy_pctl)) if n else 0.0
    loud_idx = {i for i, e in enumerate(rms) if e >= pctl - 1e-15}
    anchors = sorted(long_idx | loud_idx)
    meta = {
        "n_units": n,
        "n_anchors": len(anchors),
        "n_long": len(long_idx),
        "n_loud": len(loud_idx),
        "n_short_assign": n - len(anchors),
        "min_sec": min_sec,
        "energy_pctl": energy_pctl,
        "energy_cutoff_rms": base._round3(pctl),
        "anchor_index": anchors,
        "unit_speech_sec": [base._round3(d) for d in speech],
        "unit_rms": [base._round3(e) for e in rms],
        "is_long": [i in long_idx for i in range(n)],
        "is_loud": [i in loud_idx for i in range(n)],
    }
    return anchors, meta


def cluster_anchors_then_assign(
    x: np.ndarray,
    anchor_idx: list[int],
    thr: float,
) -> tuple[list[int], dict[str, Any], float]:
    """Cluster anchors with T2 sequential centroids, then assign the rest (or new id)."""
    t0 = time.perf_counter()
    n = len(x)
    if n == 0:
        return [], {"n": 0, "n_anchors": 0, "threshold": thr}, 0.0
    if not anchor_idx:
        labels, meta, wall = sequential_nearest_centroid(x, thr)
        meta["fallback"] = "no_anchors_t2_all"
        return labels, meta, wall

    ax = np.stack([x[i] for i in anchor_idx])
    a_labels, a_meta, _ = sequential_nearest_centroid(ax, thr)
    centroids: list[np.ndarray] = []
    counts: list[int] = []
    by_lab: dict[int, list[int]] = {}
    for loc, gi in zip(a_labels, anchor_idx, strict=True):
        by_lab.setdefault(int(loc), []).append(int(gi))
    full = [-1] * n
    for lab, idxs in sorted(by_lab.items()):
        rows = np.stack([x[i] for i in idxs])
        cent = _l2_normalize(rows.mean(axis=0, keepdims=True))[0]
        new_id = len(centroids)
        centroids.append(cent)
        counts.append(len(idxs))
        for i in idxs:
            full[i] = new_id

    n_assigned = 0
    n_new = 0
    for i in range(n):
        if full[i] >= 0:
            continue
        vec = x[i]
        sims = [float(np.dot(vec, c)) for c in centroids]
        best = int(np.argmax(sims)) if sims else 0
        if sims and sims[best] >= thr:
            full[i] = best
            counts[best] += 1
            acc = centroids[best] * (counts[best] - 1) + vec
            centroids[best] = _l2_normalize(acc.reshape(1, -1))[0]
            n_assigned += 1
        else:
            full[i] = len(centroids)
            centroids.append(np.asarray(vec, dtype=np.float64).copy())
            counts.append(1)
            n_new += 1
    wall = time.perf_counter() - t0
    meta = {
        "n": n,
        "threshold": thr,
        "n_anchors": len(anchor_idx),
        "n_anchor_labels": a_meta.get("n_labels"),
        "n_assigned_short": n_assigned,
        "n_new_from_short": n_new,
        "n_labels": len(set(full)),
        "anchor_cluster": a_meta,
    }
    return full, meta, wall


def map_ok_labels(
    n_units: int,
    ok_idx: list[int],
    labels_ok: list[int],
) -> list[int]:
    mapped: list[int | None] = [None] * n_units
    if not ok_idx:
        return [0] * n_units if n_units else []
    for lab, i in zip(labels_ok, ok_idx, strict=True):
        mapped[i] = int(lab)
    return base.fill_missing_labels(mapped)


def turns_from_unit_labels(units: list[list[Any]], labels: list[int], cfg: Any) -> list[Any]:
    if not units:
        return []
    segs, labs = base.island_segments_with_unit_labels(units, labels)
    return base.labels_to_turns(segs, labs, cfg, absorb=True)


def extract_prior_2a(results: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    quality = results.get("quality", {})
    for clip, methods in quality.items():
        row = methods.get("2A_overlap_1.5_0.75")
        if not row:
            continue
        slim = {
            "n_id": row.get("n_id"),
            "crumb_count_lt3s": row.get("crumb_count_lt3s"),
            "top1_share": row.get("top1_share"),
            "speech_sec_per_id": row.get("speech_sec_per_id"),
            "shortest_id_speech_sec": row.get("shortest_id_speech_sec"),
        }
        if "greeting_42_45" in row:
            g = row["greeting_42_45"]
            slim["greeting_distinct"] = g.get("distinct_from_global_top1")
            slim["greeting_overlap_sec_per_id"] = g.get("overlap_sec_per_id")
            slim["greeting_global_speech"] = g.get("global_speech_of_interval_ids")
        out[clip] = slim
    return out


def score_soft(clip: str, row: dict[str, Any]) -> dict[str, Any]:
    n_id = int(row.get("n_id") or 0)
    flags: dict[str, Any] = {"n_id": n_id}
    if clip == "clip01":
        g = row.get("greeting_42_45") or {}
        flags["greeting_distinct"] = bool(g.get("distinct_from_global_top1"))
        flags["greeting_n_ids"] = int(g.get("n_ids_in_interval") or 0)
        flags["greeting_cleanish"] = bool(
            g.get("distinct_from_global_top1") and int(g.get("n_ids_in_interval") or 0) == 1
        )
        gs = g.get("global_speech_of_interval_ids") or {}
        flags["greeting_id_global_s"] = max(gs.values()) if gs else 0.0
    if clip in ("clip02", "clip03"):
        flags["not_collapsed"] = n_id >= 2
        flags["not_wild_oversplit"] = n_id <= 5
    if clip == "test_ninth":
        speech = row.get("speech_sec_per_id") or {}
        vals = sorted((float(v) for v in speech.values()), reverse=True)
        third = vals[2] if len(vals) >= 3 else 0.0
        flags["has_ge3_ids"] = n_id >= 3
        flags["third_id_speech_s"] = base._round3(third)
        flags["short_secondary_survives"] = n_id >= 3 and third >= 2.0
    if clip == "test_apartments":
        speech = row.get("speech_sec_per_id") or {}
        substantial = sum(1 for v in speech.values() if float(v) >= 8.0)
        flags["n_substantial_ge8s"] = substantial
        flags["not_collapsed"] = n_id >= 2
    if clip == "concat_01_02_03":
        flags["not_collapsed"] = n_id >= 2
    return flags


def main() -> None:
    t_all = time.perf_counter()
    rss = base.RssSampler()
    rss.start()
    base.OUT.mkdir(parents=True, exist_ok=True)
    base.TIMELINES.mkdir(parents=True, exist_ok=True)
    base.WORK.mkdir(parents=True, exist_ok=True)

    prior_path = base.OUT / "results.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.is_file() else {}
    prior_2a_quality = extract_prior_2a(prior)
    timing_prior = prior.get("timing_5min", {})

    vad_cfg, diar_cfg = base.load_vad_diar_cfg()
    print(
        f"followup unit-AHC glue={base.GLUE_SEC} T1={T1_AHC} T2/T3={T2_THR} "
        f"anchor_min={ANCHOR_MIN_SEC}s energy_pctl={ENERGY_PCTL}",
        flush=True,
    )

    t_load = time.perf_counter()
    raw = SpeakerEmbedder(model="wespeaker-resnet34")
    model_load_sec = time.perf_counter() - t_load
    print(f"model_load_sec={model_load_sec:.3f}", flush=True)
    embedder = base.CountingEmbedder(raw)
    vad = base.SileroVadDetector()

    quality: dict[str, Any] = {}
    preprocess: dict[str, Any] = {}
    anchors_meta: dict[str, Any] = {}
    timing_5min: dict[str, Any] = {}

    all_clips = list(base.QUALITY_CLIPS) + [base.TIMING_CLIP]
    for clip_id, src in all_clips:
        print(f"== {clip_id} ==", flush=True)
        wav = base.copy_clip(clip_id, src)
        audio, sr = sf.read(str(wav), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        duration = float(len(audio) / sr)
        prep = base.preprocess_clip(wav, vad, vad_cfg, diar_cfg)
        units = prep["unit_lists"]
        preprocess[clip_id] = {
            k: v
            for k, v in prep.items()
            if k not in {"regions", "islands", "unit_lists"}
        }
        dump = clip_id != "timing_5min"
        min_embed = diar_cfg.embed.min_sec

        embedder.reset()
        t_emb = time.perf_counter()
        unit_vecs, n_ok = base.embed_units(audio, sr, units, embedder, min_embed)
        embed_wall = time.perf_counter() - t_emb
        n_calls = embedder.n_calls
        embed_sec = embedder.embed_sec
        x_units, ok_idx = base.stacked_ok(unit_vecs)
        print(
            f"  units={len(units)} embedded={n_ok} n_embed={n_calls} embed_sec={embed_sec:.3f}",
            flush=True,
        )

        a_idx, a_meta = select_anchors(units, audio, sr)
        anchors_meta[clip_id] = a_meta
        print(
            f"  anchors long|loud={a_meta['n_anchors']}/{len(units)} "
            f"long={a_meta['n_long']} loud={a_meta['n_loud']}",
            flush=True,
        )

        methods: dict[str, Any] = {}
        if dump:
            # T1
            for thr in T1_AHC:
                labs_ok, meta, cl = base.cluster_ahc(x_units, thr)
                full = map_ok_labels(len(units), ok_idx, labs_ok)
                turns = turns_from_unit_labels(units, full, diar_cfg)
                key = f"T1_ahc{thr:.2f}"
                methods[key] = base.method_row(
                    clip_id,
                    key,
                    turns,
                    {
                        "family": "T1",
                        "n_embed_calls": n_calls,
                        "embed_sec": base._round3(embed_sec),
                        "cluster_sec": base._round3(cl),
                        "n_units": len(units),
                        "n_units_embedded": n_ok,
                        "ahc_threshold": thr,
                        "cluster_meta": meta,
                    },
                    duration,
                    dump,
                )
            # T2
            for thr in T2_THR:
                labs_ok, meta, cl = sequential_nearest_centroid(x_units, thr)
                full = map_ok_labels(len(units), ok_idx, labs_ok)
                turns = turns_from_unit_labels(units, full, diar_cfg)
                key = f"T2_cent{thr:.2f}"
                methods[key] = base.method_row(
                    clip_id,
                    key,
                    turns,
                    {
                        "family": "T2",
                        "n_embed_calls": n_calls,
                        "embed_sec": base._round3(embed_sec),
                        "cluster_sec": base._round3(cl),
                        "n_units": len(units),
                        "n_units_embedded": n_ok,
                        "cosine_threshold": thr,
                        "cluster_meta": meta,
                    },
                    duration,
                    dump,
                )
            # T3
            for thr in T3_THR:
                labs_ok, meta, cl = cluster_anchors_then_assign(x_units, a_idx, thr)
                full = map_ok_labels(len(units), ok_idx, labs_ok)
                turns = turns_from_unit_labels(units, full, diar_cfg)
                key = f"T3_anchor{thr:.2f}"
                methods[key] = base.method_row(
                    clip_id,
                    key,
                    turns,
                    {
                        "family": "T3",
                        "n_embed_calls": n_calls,
                        "embed_sec": base._round3(embed_sec),
                        "cluster_sec": base._round3(cl),
                        "n_units": len(units),
                        "n_units_embedded": n_ok,
                        "n_anchors": a_meta["n_anchors"],
                        "cosine_threshold": thr,
                        "cluster_meta": {
                            k: meta[k]
                            for k in (
                                "n_anchors",
                                "n_anchor_labels",
                                "n_assigned_short",
                                "n_new_from_short",
                                "n_labels",
                                "threshold",
                            )
                            if k in meta
                        },
                    },
                    duration,
                    dump,
                )
            quality[clip_id] = methods

        if clip_id == "timing_5min":
            # Cluster-only timings on already-computed unit vectors.
            t1_cl = {}
            for thr in T1_AHC:
                _, _, cl = base.cluster_ahc(x_units, thr)
                t1_cl[f"{thr:.2f}"] = base._round3(cl)
            t2_cl = {}
            for thr in T2_THR:
                _, _, cl = sequential_nearest_centroid(x_units, thr)
                t2_cl[f"{thr:.2f}"] = base._round3(cl)
            t3_cl = {}
            for thr in T3_THR:
                _, _, cl = cluster_anchors_then_assign(x_units, a_idx, thr)
                t3_cl[f"{thr:.2f}"] = base._round3(cl)
            timing_5min = {
                "clip": clip_id,
                "duration_sec": base._round3(duration),
                "model_load_sec": base._round3(model_load_sec),
                "vad_sec": prep["vad_sec"],
                "n_islands": prep["n_islands"],
                "n_units": len(units),
                "n_anchors": a_meta["n_anchors"],
                "speech_sec": prep["speech_sec"],
                "unit_embed": {
                    "n_embed_calls": n_calls,
                    "embed_sec": base._round3(embed_sec),
                    "embed_wall_sec": base._round3(embed_wall),
                    "n_units_embedded": n_ok,
                    "ms_per_embed": base._round1(1000.0 * embed_sec / max(n_calls, 1)),
                },
                "cluster_sec": {"T1_ahc": t1_cl, "T2_cent": t2_cl, "T3_anchor": t3_cl},
                "prior_2A_overlap_1.5_0.75": PRIOR_2A,
                "prior_2C_ahc0.85": PRIOR_2C,
                "note": (
                    "T1/T2/T3 share one WeSpeaker pass over glued units. "
                    "T3 still embeds shorts so they can be compared to centroids "
                    "(new-speaker thr). n_embed_calls therefore matches 2C, not 2A. "
                    "2A window embeds were not re-run."
                ),
            }

    peak_kb = rss.stop()
    wall = time.perf_counter() - t_all
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    branch = subprocess.check_output(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=ROOT, text=True
    ).strip()

    scored: dict[str, Any] = {}
    for clip, methods in quality.items():
        scored[clip] = {k: score_soft(clip, v) for k, v in methods.items()}

    payload = {
        "schema_version": "1",
        "task": "D5.diar-twopass.FOLLOWUP_unit_ahc",
        "branch": branch,
        "commit_at_run_start": commit,
        "model_load_sec": base._round3(model_load_sec),
        "glue_sec": base.GLUE_SEC,
        "t1_ahc": list(T1_AHC),
        "t2_centroid_thr": list(T2_THR),
        "t3_assign_thr": list(T3_THR),
        "anchor_min_sec": ANCHOR_MIN_SEC,
        "anchor_energy_percentile": ENERGY_PCTL,
        "note": (
            "Same glued VAD units as the prior 2C run. One WeSpeaker embed per unit, "
            "then T1 AHC grid (no 0.85), T2 global nearest-centroid sequential, "
            "T3 long|loud anchors then assign. No cheap 1B/1C. No 3.0/1.5 windows. "
            "No gold. Stage-2 absorb 1.0 s / gap 0.3 s. 2A numbers copied from prior results.json."
        ),
        "prior_2A_quality": prior_2a_quality,
        "prior_timing_5min": {
            "2A": (timing_prior.get("methods") or {}).get("2A_overlap_1.5_0.75") or PRIOR_2A,
            "2C": (timing_prior.get("methods") or {}).get("2C_one_embed_per_unit") or PRIOR_2C,
        },
        "preprocess": base.jsonable(preprocess),
        "anchors": anchors_meta,
        "quality": base.jsonable(quality),
        "soft_focus_flags": scored,
        "timing_5min": timing_5min,
        "wall_sec": base._round3(wall),
        "peak_rss_mb": base._round1(peak_kb / 1024.0),
    }
    (base.OUT / "FOLLOWUP_unit_ahc.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"done wall_sec={wall:.1f} peak_rss_mb={peak_kb/1024:.1f}", flush=True)
    print(json.dumps(timing_5min.get("unit_embed", {}), sort_keys=True), flush=True)


if __name__ == "__main__":
    main()

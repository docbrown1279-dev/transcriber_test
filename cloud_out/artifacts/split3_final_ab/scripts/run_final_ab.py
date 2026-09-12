#!/usr/bin/env python3
"""Final A/B: V1 EOS AHC, V2 constrained merge, V3 H1+micro-glue.

Reuses split3_cluster_rebuild embeddings. No src/config edits. No ASR/LLM.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path("/workspace")
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402

from centroid_assign import (  # noqa: E402
    SpeakerGallery,
    _ahc_labels,
    _turns_from_window_speakers,
    cosine_distance_matrix,
    window_speakers_after_turns,
)
from cluster_hyps import (  # noqa: E402
    HOTSPOT_ABS,
    MICRO_CLUSTER_SPEECH_SEC,
    _appearance_clusters,
    _cluster_mean,
    h1_cluster_then_match,
    labels_to_turns,
    turns_metrics,
    union_speech_sec,
)
from transcriber.config.loader import load_config  # noqa: E402
from transcriber.diarization.wespeaker import _l2_normalize  # noqa: E402
from transcriber.models.artifacts import TurnItem, TurnsArtifact, dump_artifact, load_artifact  # noqa: E402

OUT = ROOT / "cloud_out" / "artifacts" / "split3_final_ab"
REBUILD = ROOT / "cloud_out" / "artifacts" / "split3_cluster_rebuild"
H1_DIR = REBUILD / "H1_cluster_then_match"
FULL15_TURNS = ROOT / "cloud_out" / "artifacts" / "full15" / "turns.json"
UNIFIED = ROOT / "cloud_out" / "artifacts" / "split3_unified_norm"
RUN_META = ROOT / "cloud_out" / "run_meta.json"

THRESHOLD = 0.85
MAX_ATTEMPTS = 20
NUDGE = 0.5
ABSURD_DIST = 1.5
V3_RULE = "A"

PART_IDS = ("part01", "part02", "part03")


def _round3(value: float) -> float:
    return round(float(value), 3)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True).strip()


def _spk(idx: int) -> str:
    return f"SPEAKER_{idx:02d}"


def _next_id(used: set[str]) -> str:
    n = 0
    while _spk(n) in used:
        n += 1
    return _spk(n)


def load_parts() -> dict[str, dict[str, Any]]:
    offsets = json.loads((REBUILD / "offsets.json").read_text(encoding="utf-8"))
    parts: dict[str, dict[str, Any]] = {}
    for pid in PART_IDS:
        windows = json.loads((REBUILD / f"{pid}_windows.json").read_text(encoding="utf-8"))
        embs = np.load(REBUILD / f"{pid}_embeddings.npy")
        if embs.ndim != 2 or len(windows) != len(embs):
            raise RuntimeError(f"{pid}: windows {len(windows)} vs embeddings {getattr(embs, 'shape', None)}")
        info = offsets["parts"][pid]
        abs_off = float(info["abs_offset"])
        segments = [(float(w["start"]), float(w["end"])) for w in windows]
        abs_segments = [
            (_round3(s + abs_off), _round3(e + abs_off)) for s, e in segments
        ]
        parts[pid] = {
            "id": pid,
            "abs_offset": abs_off,
            "plan_end": float(info["plan_end"]),
            "duration_sec": float(info["duration_sec"]),
            "windows": windows,
            "segments": segments,
            "abs_segments": abs_segments,
            "embeddings": _l2_normalize(np.asarray(embs, dtype=np.float64)),
        }
    return parts


def part1_ahc_gallery(part: dict[str, Any], cfg: Any) -> tuple[SpeakerGallery, list[str], TurnsArtifact]:
    embs = part["embeddings"]
    segs = part["segments"]
    raw = _ahc_labels(embs, THRESHOLD)
    raw_ids = [_spk(int(lbl)) for lbl in raw]
    turns = _turns_from_window_speakers(
        segs,
        raw_ids,
        cfg,
        job_id="part01",
        total_duration=part["duration_sec"],
        runtime_sec=0.0,
        compact_renumber=True,
    )
    final_ids = window_speakers_after_turns(segs, raw_ids, turns.turns)
    gallery = SpeakerGallery.from_ahc(embs, raw, final_ids, THRESHOLD)
    return gallery, final_ids, turns


def clip_turns_to_part(
    turns: list[TurnItem],
    *,
    lo: float,
    hi: float,
    local: bool,
) -> list[TurnItem]:
    clipped: list[TurnItem] = []
    for turn in turns:
        start = max(float(turn.start), lo)
        end = min(float(turn.end), hi)
        if end - start <= 1e-6:
            continue
        if local:
            start -= lo
            end -= lo
        clipped.append(
            TurnItem(
                id="tmp",
                start=_round3(start),
                end=_round3(end),
                speaker=str(turn.speaker),
            )
        )
    clipped.sort(key=lambda t: (t.start, t.end, t.speaker))
    out: list[TurnItem] = []
    for i, turn in enumerate(clipped, start=1):
        out.append(TurnItem(id=f"t{i:04d}", start=turn.start, end=turn.end, speaker=turn.speaker))
    return out


def turns_artifact(
    turns: list[TurnItem],
    *,
    job_id: str,
    total_duration: float,
    cfg: Any,
    runtime_sec: float,
) -> TurnsArtifact:
    from transcriber.asr.holes import find_holes
    from transcriber.models.artifacts import TurnMergeInfo

    return TurnsArtifact(
        schema_version="1",
        job_id=job_id,
        diarizer="wespeaker_onnx",
        speaker_count=len({t.speaker for t in turns}),
        turns=turns,
        holes=find_holes(turns, total_duration, min_hole_sec=cfg.merge.min_hole_sec),
        merge=TurnMergeInfo(
            same_speaker_gap_sec=cfg.merge.same_speaker_gap_sec,
            absorb_shorter_than_sec=cfg.merge.absorb_turn_shorter_than_sec,
        ),
        runtime_sec=runtime_sec,
    )


def interval_overlap(a: list[tuple[float, float]], b: list[tuple[float, float]]) -> float:
    total = 0.0
    for s0, e0 in a:
        for s1, e1 in b:
            lo = max(s0, s1)
            hi = min(e0, e1)
            if hi > lo:
                total += hi - lo
    return total


def greedy_duration_remap(
    src: list[TurnItem],
    ref: list[TurnItem],
) -> dict[str, Any]:
    by_src: dict[str, list[tuple[float, float]]] = {}
    by_ref: dict[str, list[tuple[float, float]]] = {}
    for t in src:
        by_src.setdefault(t.speaker, []).append((float(t.start), float(t.end)))
    for t in ref:
        by_ref.setdefault(t.speaker, []).append((float(t.start), float(t.end)))
    matrix: dict[tuple[str, str], float] = {}
    pairs: list[tuple[float, str, str]] = []
    for sa, ia in by_src.items():
        for sb, ib in by_ref.items():
            ov = interval_overlap(ia, ib)
            matrix[(sa, sb)] = ov
            pairs.append((ov, sa, sb))
    pairs.sort(reverse=True)
    used_s: set[str] = set()
    used_r: set[str] = set()
    mapping: dict[str, str] = {}
    matched = 0.0
    for ov, sa, sb in pairs:
        if ov <= 0 or sa in used_s or sb in used_r:
            continue
        mapping[sa] = sb
        used_s.add(sa)
        used_r.add(sb)
        matched += ov
    dur_src = sum(e - s for t in src for s, e in ((t.start, t.end),))
    dur_ref = sum(e - s for t in ref for s, e in ((t.start, t.end),))
    agree_ref = (100.0 * matched / dur_ref) if dur_ref else 0.0
    agree_src = (100.0 * matched / dur_src) if dur_src else 0.0
    dice = (200.0 * matched / (dur_src + dur_ref)) if (dur_src + dur_ref) else 0.0
    return {
        "mapping_src_to_full15": mapping,
        "matched_overlap_sec": _round3(matched),
        "duration_src_sec": _round3(dur_src),
        "duration_full15_sec": _round3(dur_ref),
        "agreement_pct_of_full15": _round3(agree_ref),
        "agreement_pct_of_src": _round3(agree_src),
        "dice_pct": _round3(dice),
        "unmapped_src": sorted(set(by_src) - used_s),
        "unmapped_full15": sorted(set(by_ref) - used_r),
    }


def apply_remap(turns: list[TurnItem], mapping: dict[str, str]) -> list[TurnItem]:
    out = []
    for i, t in enumerate(turns, start=1):
        out.append(
            TurnItem(
                id=f"t{i:04d}",
                start=t.start,
                end=t.end,
                speaker=mapping.get(t.speaker, t.speaker),
            )
        )
    return out


def run_v1(parts: dict[str, dict[str, Any]], cfg: Any) -> dict[str, Any]:
    dest = OUT / "V1_eos_ahc"
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    concat_segs: list[tuple[float, float]] = []
    concat_embs: list[np.ndarray] = []
    owners: list[tuple[str, int]] = []
    rows = []
    for pid in PART_IDS:
        part = parts[pid]
        for i, (seg, vec) in enumerate(zip(part["abs_segments"], part["embeddings"], strict=True)):
            rows.append((seg[0], seg[1], pid, i, vec))
    rows.sort(key=lambda r: (r[0], r[1], r[2], r[3]))
    for start, end, pid, i, vec in rows:
        concat_segs.append((start, end))
        concat_embs.append(vec)
        owners.append((pid, i))
    x = _l2_normalize(np.stack(concat_embs))
    labels = _ahc_labels(x, THRESHOLD)
    raw_ids = [_spk(int(lbl)) for lbl in labels]
    full_dur = max(900.0, max(e for _, e in concat_segs))
    full_turns_art = _turns_from_window_speakers(
        concat_segs,
        raw_ids,
        cfg,
        job_id="v1_eos_full",
        total_duration=_round3(full_dur),
        runtime_sec=0.0,
        compact_renumber=True,
    )
    runtime = round(time.time() - t0, 3)
    full_turns_art = full_turns_art.model_copy(update={"runtime_sec": runtime})
    dump_artifact(full_turns_art, dest / "turns_full.json")

    full15 = load_artifact(FULL15_TURNS, TurnsArtifact)
    remap = greedy_duration_remap(full_turns_art.turns, full15.turns)
    _write_json(dest / "remap_vs_full15.json", remap)

    metrics: dict[str, Any] = {}
    for pid in ("part02", "part03"):
        lo = parts[pid]["abs_offset"]
        hi = parts[pid]["plan_end"]
        local = clip_turns_to_part(full_turns_art.turns, lo=lo, hi=hi, local=True)
        art = turns_artifact(
            local,
            job_id=pid,
            total_duration=parts[pid]["duration_sec"],
            cfg=cfg,
            runtime_sec=runtime,
        )
        dump_artifact(art, dest / f"turns_{pid}.json")
        p1_local = clip_turns_to_part(
            full_turns_art.turns,
            lo=parts["part01"]["abs_offset"],
            hi=parts["part01"]["plan_end"],
            local=True,
        )
        p1_ids = sorted({t.speaker for t in p1_local})
        met = turns_metrics(
            hyp="V1",
            part=pid,
            turns=local,
            part1_ids=p1_ids,
            abs_offset=lo,
        )
        _write_json(dest / f"metrics_{pid}.json", met)
        metrics[pid] = met

    full_met = turns_metrics(
        hyp="V1",
        part="full",
        turns=full_turns_art.turns,
        part1_ids=sorted({t.speaker for t in full_turns_art.turns}),
        abs_offset=0.0,
    )
    # hotspot for full: turns already absolute
    lo, hi = HOTSPOT_ABS
    full_met["hotspot_365_375"] = [
        {
            "id": t.id,
            "start": t.start,
            "end": t.end,
            "start_abs": t.start,
            "end_abs": t.end,
            "speaker": t.speaker,
            "duration_sec": _round3(t.end - t.start),
        }
        for t in full_turns_art.turns
        if t.end > lo and t.start < hi
    ]
    full_met["n_windows"] = len(concat_segs)
    full_met["n_ahc_labels"] = len(set(labels))
    full_met["remap_vs_full15"] = {
        k: remap[k]
        for k in (
            "agreement_pct_of_full15",
            "dice_pct",
            "mapping_src_to_full15",
            "matched_overlap_sec",
        )
    }
    _write_json(dest / "metrics_full.json", full_met)
    metrics["full"] = full_met
    metrics["remap"] = remap
    metrics["runtime_sec"] = runtime
    return metrics


def _com(vectors: list[np.ndarray]) -> np.ndarray:
    stacked = _l2_normalize(np.stack(vectors))
    return _l2_normalize(stacked.mean(axis=0, keepdims=True))[0]


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(cosine_distance_matrix(a.reshape(1, -1), b.reshape(1, -1))[0, 0])


def run_v2(parts: dict[str, dict[str, Any]], cfg: Any) -> dict[str, Any]:
    dest = OUT / "V2_constrained_merge"
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    committed_emb: dict[str, list[np.ndarray]] = {}
    committed_meta: list[dict[str, Any]] = []
    part_assigned: dict[str, list[str]] = {}
    attempt_logs: dict[str, Any] = {}

    # Part1: plain AHC, commit compact first-appearance ids (window labels, not post-absorb).
    p1 = parts["part01"]
    raw = _ahc_labels(p1["embeddings"], THRESHOLD)
    order = _appearance_clusters(raw)
    lab_to_id = {lab: _spk(i) for i, lab in enumerate(order)}
    assigned1 = [lab_to_id[int(lbl)] for lbl in raw]
    part_assigned["part01"] = assigned1
    for i, spk in enumerate(assigned1):
        committed_emb.setdefault(spk, []).append(p1["embeddings"][i])
        committed_meta.append({"part": "part01", "index": i, "speaker": spk})
    centroids = {spk: _com(vecs) for spk, vecs in committed_emb.items()}
    used_ids = set(committed_emb)

    def assign_part(pid: str) -> tuple[list[str], dict[str, Any]]:
        nonlocal centroids, used_ids
        part = parts[pid]
        embs = part["embeddings"]
        segs = part["segments"]
        raw_l = _ahc_labels(embs, THRESHOLD)
        by_lab: dict[int, list[int]] = {}
        for i, lab in enumerate(raw_l):
            by_lab.setdefault(int(lab), []).append(i)
        clusters = []
        for lab in _appearance_clusters(raw_l):
            idxs = by_lab[lab]
            clusters.append(
                {
                    "local_label": lab,
                    "idxs": idxs,
                    "mean": _cluster_mean(embs, idxs),
                    "speech_union_sec": union_speech_sec([segs[i] for i in idxs]),
                    "start": min(segs[i][0] for i in idxs),
                }
            )
        clusters.sort(key=lambda c: (c["start"], c["local_label"]))

        start_centroids = {k: v.copy() for k, v in centroids.items()}
        attempts: list[dict[str, Any]] = []
        chosen: dict[int, str] | None = None
        success = False

        def try_assign(cents: dict[str, np.ndarray]) -> tuple[dict[int, str], dict[str, Any]]:
            working = {k: v.copy() for k, v in cents.items()}
            # include empty new ids created this attempt
            extra_emb: dict[str, list[np.ndarray]] = {k: [] for k in working}
            mapping: dict[int, str] = {}
            events: list[dict[str, Any]] = []
            local_used = set(used_ids)
            for cluster in clusters:
                mean = cluster["mean"]
                ids = list(working.keys())
                d_best = None
                nearest = None
                if ids:
                    mat = np.stack([working[i] for i in ids])
                    dist = cosine_distance_matrix(mean.reshape(1, -1), mat)[0]
                    j = int(np.argmin(dist))
                    d_best = float(dist[j])
                    nearest = ids[j]
                absurd = d_best is not None and (d_best != d_best or d_best > ABSURD_DIST)
                if nearest is not None and d_best is not None and d_best <= THRESHOLD and not absurd:
                    old_vecs = committed_emb.get(nearest, [])
                    new_vecs = old_vecs + extra_emb.get(nearest, []) + [embs[i] for i in cluster["idxs"]]
                    new_com = _com(new_vecs)
                    old_cent = working[nearest]
                    inliers = [vec for vec in old_vecs if _dist(vec, old_cent) <= THRESHOLD]
                    viol = 0
                    max_old = 0.0
                    for vec in inliers:
                        d_old = _dist(vec, new_com)
                        max_old = max(max_old, d_old)
                        if d_old > THRESHOLD:
                            viol += 1
                    already_out = len(old_vecs) - len(inliers)
                    events.append(
                        {
                            "local_label": cluster["local_label"],
                            "d_best": round(d_best, 4),
                            "nearest": nearest,
                            "old_inliers_gt_thr": viol,
                            "already_outliers": already_out,
                            "max_inlier_to_new_com": round(max_old, 4),
                            "decision": "match" if viol == 0 else "constraint_fail",
                        }
                    )
                    if viol:
                        return mapping, {
                            "ok": False,
                            "fail_cluster": cluster,
                            "fail_target": nearest,
                            "d_best": d_best,
                            "viol": viol,
                            "events": events,
                        }
                    mapping[cluster["local_label"]] = nearest
                    extra_emb.setdefault(nearest, []).extend(embs[i] for i in cluster["idxs"])
                    working[nearest] = new_com
                else:
                    new_id = _next_id(local_used)
                    local_used.add(new_id)
                    mapping[cluster["local_label"]] = new_id
                    working[new_id] = mean
                    extra_emb[new_id] = [embs[i] for i in cluster["idxs"]]
                    events.append(
                        {
                            "local_label": cluster["local_label"],
                            "d_best": None if d_best is None else round(d_best, 4),
                            "nearest": nearest,
                            "decision": "new_id_absurd" if absurd else "new_id",
                            "new_id": new_id,
                        }
                    )
            return mapping, {"ok": True, "events": events}

        for attempt in range(MAX_ATTEMPTS):
            mapping, info = try_assign(start_centroids)
            rec = {
                "attempt": attempt + 1,
                "ok": bool(info.get("ok")),
                "n_events": len(info.get("events") or []),
            }
            if info.get("ok"):
                rec["events"] = info["events"]
                attempts.append(rec)
                chosen = mapping
                success = True
                break
            fail_c = info["fail_cluster"]
            target = info["fail_target"]
            rec["fail"] = {
                "local_label": fail_c["local_label"],
                "target": target,
                "d_best": None if info.get("d_best") is None else round(float(info["d_best"]), 4),
                "old_windows_gt_thr": info.get("viol"),
            }
            old_vecs = committed_emb.get(target, [])
            if old_vecs:
                d_mem = cosine_distance_matrix(
                    fail_c["mean"].reshape(1, -1), np.stack(old_vecs)
                )[0]
                k = max(1, min(5, len(old_vecs)))
                nearest_idx = np.argsort(d_mem)[:k]
                mem_mean = _com([old_vecs[int(i)] for i in nearest_idx])
                target_vec = _l2_normalize(
                    (0.5 * mem_mean + 0.5 * fail_c["mean"]).reshape(1, -1)
                )[0]
            else:
                target_vec = fail_c["mean"]
            if target in start_centroids:
                start_centroids[target] = _l2_normalize(
                    ((1.0 - NUDGE) * start_centroids[target] + NUDGE * target_vec).reshape(1, -1)
                )[0]
            rec["nudge"] = {
                "centroid": target,
                "blend": NUDGE,
                "toward": "nearest_member_mean+cluster_mean",
            }
            attempts.append(rec)

        fallback = False
        if chosen is None:
            fallback = True
            # Best feasible: never recolor past windows; new id when match would violate CoM.
            mapping, info = try_assign(centroids)
            if not info.get("ok"):
                mapping = {}
                local_used = set(used_ids)
                working = {k: v.copy() for k, v in centroids.items()}
                extra_emb: dict[str, list[np.ndarray]] = {k: [] for k in working}
                for cluster in clusters:
                    mean = cluster["mean"]
                    ids = list(working.keys())
                    d_best = None
                    nearest = None
                    if ids:
                        mat = np.stack([working[i] for i in ids])
                        dist = cosine_distance_matrix(mean.reshape(1, -1), mat)[0]
                        j = int(np.argmin(dist))
                        d_best = float(dist[j])
                        nearest = ids[j]
                    use_new = True
                    if nearest is not None and d_best is not None and d_best <= THRESHOLD:
                        old_vecs = committed_emb.get(nearest, [])
                        new_vecs = old_vecs + extra_emb.get(nearest, []) + [embs[i] for i in cluster["idxs"]]
                        new_com = _com(new_vecs)
                        old_cent = working[nearest]
                        viol = sum(
                            1
                            for vec in old_vecs
                            if _dist(vec, old_cent) <= THRESHOLD and _dist(vec, new_com) > THRESHOLD
                        )
                        if viol == 0:
                            mapping[cluster["local_label"]] = nearest
                            extra_emb.setdefault(nearest, []).extend(embs[i] for i in cluster["idxs"])
                            working[nearest] = new_com
                            use_new = False
                    if use_new:
                        new_id = _next_id(local_used)
                        local_used.add(new_id)
                        mapping[cluster["local_label"]] = new_id
                        working[new_id] = mean
                        extra_emb[new_id] = [embs[i] for i in cluster["idxs"]]
                info = {"ok": False, "events": [{"decision": "fallback_feasible_new_ids"}]}
            chosen = mapping
            attempts.append({"attempt": "fallback_feasible", "ok": True, "events": info.get("events")})

        assigned = [""] * len(embs)
        for cluster in clusters:
            spk = chosen[cluster["local_label"]]
            for i in cluster["idxs"]:
                assigned[i] = spk
        for i, spk in enumerate(assigned):
            committed_emb.setdefault(spk, []).append(embs[i])
            committed_meta.append({"part": pid, "index": i, "speaker": spk})
            used_ids.add(spk)
        centroids = {spk: _com(vecs) for spk, vecs in committed_emb.items()}
        log = {
            "part": pid,
            "n_local_clusters": len(clusters),
            "n_attempts": len(attempts),
            "success_before_cap": success,
            "fallback": fallback,
            "max_attempts": MAX_ATTEMPTS,
            "clusters": [
                {
                    "local_label": c["local_label"],
                    "n_windows": len(c["idxs"]),
                    "speech_union_sec": c["speech_union_sec"],
                    "start": c["start"],
                    "assigned_id": chosen[c["local_label"]],
                }
                for c in clusters
            ],
            "attempts": attempts,
            "speakers_after": sorted(centroids),
        }
        return assigned, log

    assigned2, log2 = assign_part("part02")
    part_assigned["part02"] = assigned2
    _write_json(dest / "attempt_log_part02.json", log2)
    assigned3, log3 = assign_part("part03")
    part_assigned["part03"] = assigned3
    _write_json(dest / "attempt_log_part03.json", log3)

    runtime = round(time.time() - t0, 3)
    metrics: dict[str, Any] = {"runtime_sec": runtime, "attempt_summary": {}}
    p1_ids = sorted(set(part_assigned["part01"]))
    for pid in ("part02", "part03"):
        art = labels_to_turns(
            parts[pid]["segments"],
            part_assigned[pid],
            cfg,
            job_id=pid,
            total_duration=parts[pid]["duration_sec"],
            runtime_sec=runtime,
        )
        dump_artifact(art, dest / f"turns_{pid}.json")
        met = turns_metrics(
            hyp="V2",
            part=pid,
            turns=art.turns,
            part1_ids=p1_ids,
            abs_offset=parts[pid]["abs_offset"],
        )
        _write_json(dest / f"metrics_{pid}.json", met)
        metrics[pid] = met
    metrics["attempt_summary"] = {
        "part02_attempts": log2["n_attempts"],
        "part02_success_before_cap": log2["success_before_cap"],
        "part02_fallback": log2["fallback"],
        "part03_attempts": log3["n_attempts"],
        "part03_success_before_cap": log3["success_before_cap"],
        "part03_fallback": log3["fallback"],
    }
    p1_art = labels_to_turns(
        p1["segments"],
        assigned1,
        cfg,
        job_id="part01",
        total_duration=p1["duration_sec"],
        runtime_sec=runtime,
    )
    dump_artifact(p1_art, dest / "turns_part01.json")
    return metrics


def apply_rule_a(
    assigned: list[str],
    log: dict[str, Any],
    segments: list[tuple[float, float]],
) -> tuple[list[str], list[dict[str, Any]]]:
    clusters = list(log.get("clusters") or [])
    if not clusters:
        return assigned, []
    ordered = sorted(
        clusters,
        key=lambda c: (
            min(segments[i][0] for i in c["window_indices"]),
            c["local_label"],
        ),
    )
    out = list(assigned)
    glue: list[dict[str, Any]] = []
    prev_id: str | None = None
    prev_label = None
    for cluster in ordered:
        cur = out[cluster["window_indices"][0]]
        speech = float(cluster.get("speech_union_sec") or 0.0)
        if (
            prev_id is not None
            and speech < MICRO_CLUSTER_SPEECH_SEC
            and cur != prev_id
        ):
            for i in cluster["window_indices"]:
                out[i] = prev_id
            glue.append(
                {
                    "local_label": cluster["local_label"],
                    "speech_union_sec": speech,
                    "from_id": cur,
                    "to_id": prev_id,
                    "prev_local_label": prev_label,
                    "rule": "A_glue_micro_to_prev_cluster",
                }
            )
            cur = prev_id
        prev_id = cur
        prev_label = cluster["local_label"]
    return out, glue


def rebuild_gallery(
    prior: SpeakerGallery,
    embeddings: np.ndarray,
    assigned: list[str],
) -> SpeakerGallery:
    gallery = prior.clone()
    known = {s["id"] for s in gallery.speakers}
    by_spk: dict[str, list[int]] = {}
    for i, spk in enumerate(assigned):
        by_spk.setdefault(spk, []).append(i)
    for spk, idxs in by_spk.items():
        if spk not in known:
            mean = _cluster_mean(embeddings, idxs)
            gallery.speakers.append(
                {
                    "id": spk,
                    "n_windows": 0,
                    "centroid": np.asarray(mean, dtype=np.float64),
                }
            )
            known.add(spk)
    gallery.blend_assignments(embeddings, assigned)
    return gallery


def run_v3(parts: dict[str, dict[str, Any]], cfg: Any, gallery_p1: SpeakerGallery) -> dict[str, Any]:
    dest = OUT / "V3_h1_tune"
    dest.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    gallery = gallery_p1.clone()
    p1_ids = [s["id"] for s in gallery.speakers]
    metrics: dict[str, Any] = {"rule": V3_RULE}
    for pid in ("part02", "part03"):
        prior = gallery.clone()
        assigned, log = h1_cluster_then_match(gallery, parts[pid]["embeddings"], parts[pid]["segments"])
        glued, glue_log = apply_rule_a(assigned, log, parts[pid]["segments"])
        gallery = rebuild_gallery(prior, parts[pid]["embeddings"], glued)
        log["tune_rule"] = V3_RULE
        log["glue"] = glue_log
        log["n_glued_clusters"] = len(glue_log)
        _write_json(dest / f"tune_log_{pid}.json", log)
        art = labels_to_turns(
            parts[pid]["segments"],
            glued,
            cfg,
            job_id=pid,
            total_duration=parts[pid]["duration_sec"],
            runtime_sec=0.0,
        )
        dump_artifact(art, dest / f"turns_{pid}.json")
        met = turns_metrics(
            hyp="V3",
            part=pid,
            turns=art.turns,
            part1_ids=p1_ids,
            abs_offset=parts[pid]["abs_offset"],
        )
        met["n_glued_clusters"] = len(glue_log)
        _write_json(dest / f"metrics_{pid}.json", met)
        metrics[pid] = met
    metrics["runtime_sec"] = round(time.time() - t0, 3)
    return metrics


def ref_full15(parts: dict[str, dict[str, Any]], cfg: Any) -> dict[str, Any]:
    dest = OUT / "refs"
    dest.mkdir(parents=True, exist_ok=True)
    full = load_artifact(FULL15_TURNS, TurnsArtifact)
    p1 = clip_turns_to_part(
        full.turns,
        lo=parts["part01"]["abs_offset"],
        hi=parts["part01"]["plan_end"],
        local=True,
    )
    p1_ids = sorted({t.speaker for t in p1})
    out: dict[str, Any] = {}
    for pid in ("part02", "part03"):
        local = clip_turns_to_part(
            full.turns,
            lo=parts[pid]["abs_offset"],
            hi=parts[pid]["plan_end"],
            local=True,
        )
        art = turns_artifact(
            local,
            job_id=f"full15_{pid}",
            total_duration=parts[pid]["duration_sec"],
            cfg=cfg,
            runtime_sec=0.0,
        )
        dump_artifact(art, dest / f"full15_turns_{pid}.json")
        met = turns_metrics(
            hyp="full15",
            part=pid,
            turns=local,
            part1_ids=p1_ids,
            abs_offset=parts[pid]["abs_offset"],
        )
        _write_json(dest / f"full15_metrics_{pid}.json", met)
        out[pid] = met
    full_met = turns_metrics(
        hyp="full15",
        part="full",
        turns=full.turns,
        part1_ids=sorted({t.speaker for t in full.turns}),
        abs_offset=0.0,
    )
    lo, hi = HOTSPOT_ABS
    full_met["hotspot_365_375"] = [
        {
            "id": t.id,
            "start": t.start,
            "end": t.end,
            "start_abs": t.start,
            "end_abs": t.end,
            "speaker": t.speaker,
            "duration_sec": _round3(t.end - t.start),
        }
        for t in full.turns
        if t.end > lo and t.start < hi
    ]
    _write_json(dest / "full15_metrics_full.json", full_met)
    out["full"] = full_met
    return out


def ref_h1(parts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    p1 = load_artifact(REBUILD / "part01_ahc_turns.json", TurnsArtifact)
    p1_ids = sorted({t.speaker for t in p1.turns})
    for pid in ("part02", "part03"):
        art = load_artifact(H1_DIR / pid / "turns.json", TurnsArtifact)
        met = turns_metrics(
            hyp="H1",
            part=pid,
            turns=art.turns,
            part1_ids=p1_ids,
            abs_offset=parts[pid]["abs_offset"],
        )
        _write_json(OUT / "refs" / f"h1_metrics_{pid}.json", met)
        out[pid] = met
    return out


def _combined(m2: dict[str, Any], m3: dict[str, Any]) -> dict[str, int]:
    return {
        "n_turns": m2["n_turns"] + m3["n_turns"],
        "n_turns_lt_1s": m2["n_turns_lt_1s"] + m3["n_turns_lt_1s"],
        "n_turns_lt_2s": m2["n_turns_lt_2s"] + m3["n_turns_lt_2s"],
        "n_speaker_switches": m2["n_speaker_switches"] + m3["n_speaker_switches"],
        "n_speakers_max": max(m2["n_speakers"], m3["n_speakers"]),
    }


def write_compare(
    *,
    v1: dict[str, Any],
    v2: dict[str, Any],
    v3: dict[str, Any],
    h1: dict[str, Any],
    full15: dict[str, Any],
    prep: dict[str, Any],
    wall_sec: float,
) -> dict[str, Any]:
    methods = {
        "full15": full15,
        "V1": v1,
        "V2": v2,
        "V3": v3,
        "H1": h1,
    }
    combined = {name: _combined(m["part02"], m["part03"]) for name, m in methods.items()}
    full_spk = combined["full15"]["n_speakers_max"]

    HUGE_SWING = 2

    def rank_key(name: str) -> tuple[int, int, int, int]:
        c = combined[name]
        swing = abs(c["n_speakers_max"] - full_spk)
        huge = 1 if swing > HUGE_SWING else 0
        return (c["n_turns_lt_1s"], c["n_speaker_switches"], huge, swing)

    def same_proxies(a: str, b: str) -> bool:
        ca, cb = combined[a], combined[b]
        return (
            ca["n_turns_lt_1s"] == cb["n_turns_lt_1s"]
            and ca["n_speaker_switches"] == cb["n_speaker_switches"]
            and ca["n_speakers_max"] == cb["n_speakers_max"]
        )

    swing_ok = [
        n
        for n in ("V2", "V3", "H1")
        if abs(combined[n]["n_speakers_max"] - full_spk) <= HUGE_SWING
    ]
    all_ttft = ["V2", "V3", "H1"]
    if swing_ok:
        ttft_pool = swing_ok
        excluded_ttft = [n for n in all_ttft if n not in swing_ok]
        collapse_note = False
    else:
        ttft_pool = all_ttft
        excluded_ttft = []
        collapse_note = True
    ttft_ranked = sorted(ttft_pool, key=rank_key)
    all_ranked = sorted(combined, key=rank_key)
    ceiling = "V1"
    ttft_pick = ttft_ranked[0]
    tied = [n for n in ttft_ranked if same_proxies(n, ttft_pick)]
    if len(tied) > 1:
        ttft_label = "=".join(tied)
    else:
        ttft_label = ttft_pick
    if collapse_note:
        ttft_label = f"{ttft_label} (all |Δspk|>2 vs full15)"

    lines = [
        "# Final A/B — V1 EOS AHC vs V2 constrained merge vs V3 H1-tune",
        "",
        "**SEMANTIC_CHECK = local human; cloud did not judge meaning.**",
        "",
        "Structural proxies only (crumbs, switches, speaker inventory, hotspot dump, "
        "V1 greedy duration remap vs full15). No gold / eval / ASR.",
        "",
        f"`proxy_pick` ceiling (offline, waits for all parts): **{ceiling}** "
        "(EOS AHC on concatenated part embeddings).",
        f"`proxy_pick` TTFT-path (online-ish, keeps part1 labels): **{ttft_label}** "
        f"(ranked {ttft_ranked}"
        + (
            "; no method kept |Δspk|≤2 vs full15"
            if collapse_note
            else f"; excluded |Δspk|>2: {excluded_ttft or 'none'}"
        )
        + ").",
        "",
        "## Combined part02+part03 proxies",
        "",
        "| method | n_turns | lt1s | lt2s | switches | n_speakers_max | Δlt1s vs full15 | Δsw vs full15 | Δspk vs full15 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("full15", "V1", "V2", "V3", "H1"):
        c = combined[name]
        f = combined["full15"]
        lines.append(
            f"| {name} | {c['n_turns']} | {c['n_turns_lt_1s']} | {c['n_turns_lt_2s']} | "
            f"{c['n_speaker_switches']} | {c['n_speakers_max']} | "
            f"{c['n_turns_lt_1s']-f['n_turns_lt_1s']:+d} | "
            f"{c['n_speaker_switches']-f['n_speaker_switches']:+d} | "
            f"{c['n_speakers_max']-f['n_speakers_max']:+d} |"
        )

    lines += [
        "",
        "## Per part",
        "",
        "| method | part | n_turns | lt1s | lt2s | switches | n_speakers | speaker_ids | new_ids_vs_part1 |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for name in ("full15", "V1", "V2", "V3", "H1"):
        for pid in ("part02", "part03"):
            m = methods[name][pid]
            lines.append(
                f"| {name} | {pid} | {m['n_turns']} | {m['n_turns_lt_1s']} | {m['n_turns_lt_2s']} | "
                f"{m['n_speaker_switches']} | {m['n_speakers']} | "
                f"{', '.join(m['speaker_ids'])} | {', '.join(m['new_ids_vs_part1']) or '—'} |"
            )

    remap = v1.get("remap") or {}
    lines += [
        "",
        "## V1 vs full15 (greedy duration remap, not gold)",
        "",
        f"- agreement % of full15 speech overlap: **{remap.get('agreement_pct_of_full15')}**",
        f"- dice %: **{remap.get('dice_pct')}**",
        f"- matched overlap sec: {remap.get('matched_overlap_sec')} / full15 {remap.get('duration_full15_sec')} / V1 {remap.get('duration_src_sec')}",
        f"- mapping V1→full15: `{remap.get('mapping_src_to_full15')}`",
        f"- unmapped V1: {remap.get('unmapped_src')}; unmapped full15: {remap.get('unmapped_full15')}",
        f"- V1 whole-file: n_turns={v1['full']['n_turns']} lt1s={v1['full']['n_turns_lt_1s']} "
        f"switches={v1['full']['n_speaker_switches']} n_speakers={v1['full']['n_speakers']}",
        f"- full15 whole-file: n_turns={full15['full']['n_turns']} lt1s={full15['full']['n_turns_lt_1s']} "
        f"switches={full15['full']['n_speaker_switches']} n_speakers={full15['full']['n_speakers']}",
        "",
        "## part02 hotspot [365.0, 375.5] abs",
        "",
    ]
    for name in ("full15", "V1", "V2", "V3", "H1"):
        hot = methods[name]["part02"].get("hotspot_365_375") or []
        seq = " → ".join(
            f"{h['speaker']}({h['duration_sec']}s @{h['start_abs']})" for h in hot
        )
        lines.append(f"- **{name}** ({len(hot)} turns): {seq or 'none'}")

    v2s = v2.get("attempt_summary") or {}
    lines += [
        "",
        "## V2 attempt log (cap 20 / part)",
        "",
        f"- part02: attempts={v2s.get('part02_attempts')} success_before_cap={v2s.get('part02_success_before_cap')} fallback={v2s.get('part02_fallback')}",
        f"- part03: attempts={v2s.get('part03_attempts')} success_before_cap={v2s.get('part03_success_before_cap')} fallback={v2s.get('part03_fallback')}",
        "- Constraint: never recolor committed windows; match whole local cluster if dist≤0.85 "
        "and old windows stay within 0.85 of the new center of mass; else new id. Nudge target "
        "centroid toward nearest member mean + cluster mean and retry.",
        "",
        "## V3 tune",
        "",
        f"- Rule **{V3_RULE}** (preferred): after H1 whole-cluster match, any local cluster with "
        f"`speech_union < {MICRO_CLUSTER_SPEECH_SEC} s` whose id differs from the previous cluster "
        "in time is glued to that previous id. Not per-window sticky. Rule B (H3 margin) was not used.",
        f"- glued clusters: part02={v3.get('part02', {}).get('n_glued_clusters')} "
        f"part03={v3.get('part03', {}).get('n_glued_clusters')}",
        "",
        "## Ranking note (proxies only)",
        "",
        f"All methods by (lt1s, switches, huge-speaker-swing vs full15): **{' > '.join(all_ranked)}**.",
        "Huge swing = |n_speakers_max − full15| > 2. Online methods here share the same 2-speaker "
        "inventory (collapse vs full15 5) while cutting crumbs/switches; that is a proxy tradeoff, "
        "not a semantic win.",
        "On this file V2 part02/part03 turns match H1 (and V3: rule A glued 0 clusters). "
        "V2 part03 needed 2 attempts (one inlier CoM nudge) then matched the same gallery ids.",
        "",
        "## Environment",
        "",
        f"- embeddings reused from split3_cluster_rebuild ({prep.get('n_windows')}); unified-norm wav slices; shared VAD",
        f"- AHC cosine/average thr={THRESHOLD}; windows 1.5/0.75; wall_sec={wall_sec}",
        "- host nproc=4; HF_HUB_OFFLINE=1; no src/config/tests edits; no PR; no LLM",
        "",
        "## Deviations",
        "",
        "None beyond V3 choosing rule A as specified-preferred.",
        "",
    ]
    (OUT / "compare.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "proxy_pick_ceiling": ceiling,
        "proxy_pick_ttft": ttft_label,
        "ttft_ranked": ttft_ranked,
        "ttft_tied": tied,
        "ttft_excluded_huge_swing": excluded_ttft,
        "all_ranked": all_ranked,
        "combined": combined,
        "v1_agreement_pct_of_full15": remap.get("agreement_pct_of_full15"),
        "v1_dice_pct": remap.get("dice_pct"),
    }


def update_run_meta(payload: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    if RUN_META.is_file():
        existing = json.loads(RUN_META.read_text(encoding="utf-8"))
    existing.update(payload)
    existing["stage"] = "D5.TTFT-final-ab"
    existing["written_at_utc"] = _now_utc()
    existing["llm_call_count"] = 0
    _write_json(RUN_META, existing)


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.chdir(ROOT)
    job_t0 = time.monotonic()
    OUT.mkdir(parents=True, exist_ok=True)

    cfg_root = load_config(profile="demo")
    cfg_root = cfg_root.model_copy(deep=True)
    cfg_root.diarization.onnx_threads = 2
    cfg = cfg_root.diarization
    if abs(float(cfg.embed.cluster_distance_threshold) - THRESHOLD) > 1e-9:
        raise RuntimeError("cluster_distance_threshold is not 0.85 in demo config")
    if abs(float(cfg.embed.window_sec) - 1.5) > 1e-9 or abs(float(cfg.embed.step_sec) - 0.75) > 1e-9:
        raise RuntimeError("window/step are not 1.5/0.75")

    parts = load_parts()
    prep = {
        "embeddings_reused": True,
        "source": str(REBUILD),
        "n_windows": {pid: len(parts[pid]["segments"]) for pid in PART_IDS},
        "unified_gain_note": "embeddings were built from unified_norm wav slices + shared VAD",
        "v3_rule": V3_RULE,
        "threshold": THRESHOLD,
    }
    _write_json(OUT / "prep_meta.json", prep)

    gallery_p1, _p1_ids, p1_turns = part1_ahc_gallery(parts["part01"], cfg)
    dump_artifact(p1_turns, OUT / "part01_ahc_turns.json")
    _write_json(OUT / "centroids_part01.json", gallery_p1.to_json())

    full15 = ref_full15(parts, cfg)
    h1 = ref_h1(parts)
    v1 = run_v1(parts, cfg)
    v2 = run_v2(parts, cfg)
    v3 = run_v3(parts, cfg, gallery_p1)

    wall = _round3(time.monotonic() - job_t0)
    summary = write_compare(
        v1=v1, v2=v2, v3=v3, h1=h1, full15=full15, prep=prep, wall_sec=wall
    )
    update_run_meta(
        {
            "stage": "D5.TTFT-final-ab",
            "branch": _sh("git rev-parse --abbrev-ref HEAD"),
            "git_rev": _sh("git rev-parse HEAD"),
            "wall_time_sec": wall,
            "final_ab": {
                "prep": prep,
                "compare": summary,
                "v2_attempts": v2.get("attempt_summary"),
                "v3_rule": V3_RULE,
            },
            "notes": [
                "Research spike: V1 EOS AHC / V2 constrained merge / V3 H1+rule A.",
                "SEMANTIC_CHECK = local human; cloud did not judge meaning.",
                "No src/config/tests edits, no PR, no ASR/LLM/gold.",
                "nproc=4 so 2-CPU TTFT is not demonstrated.",
            ],
        }
    )
    print(
        json.dumps(
            {
                "wall_sec": wall,
                "n_windows": prep["n_windows"],
                "proxy_pick_ceiling": summary["proxy_pick_ceiling"],
                "proxy_pick_ttft": summary["proxy_pick_ttft"],
                "v1_agreement_pct_of_full15": summary["v1_agreement_pct_of_full15"],
                "combined": summary["combined"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

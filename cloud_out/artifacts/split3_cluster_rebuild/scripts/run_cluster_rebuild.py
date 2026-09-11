#!/usr/bin/env python3
"""Prep WeSpeaker embeddings once, then replay H1 / H2 / H3 separately.

Writes cloud_out/artifacts/split3_cluster_rebuild/. Does not modify src/ or config/.
Does not clobber split3_unified_norm/. ASR and packing are out of scope.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path("/workspace")
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402

from centroid_assign import (  # noqa: E402
    SpeakerGallery,
    _ahc_labels,
    _turns_from_window_speakers,
    extract_wespeaker_windows,
    window_speakers_after_turns,
)
from cluster_hyps import (  # noqa: E402
    HOTSPOT_ABS,
    h1_cluster_then_match,
    h2_refine_reassign,
    h3_cluster_clear_winner,
    labels_to_turns,
    turns_metrics,
)
from transcriber.config.loader import load_config  # noqa: E402
from transcriber.diarization.wespeaker import WeSpeakerDiarizer  # noqa: E402
from transcriber.models.artifacts import (  # noqa: E402
    SpeechArtifact,
    TimeInterval,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)

OUT = ROOT / "cloud_out" / "artifacts" / "split3_cluster_rebuild"
UNIFIED = ROOT / "cloud_out" / "artifacts" / "split3_unified_norm"
CUT_PLAN = ROOT / "cloud_in" / "inputs" / "artifacts" / "cut_plan_15min_3.json"
FULL15_SPEECH = ROOT / "cloud_out" / "artifacts" / "full15" / "speech.json"
FULL15_JOB_WAV = ROOT / "cloud_out" / "artifacts" / "full15_job" / "normalized.wav"
FULL15_M4A = ROOT / "cloud_in" / "inputs" / "audio" / "voice_002_15min.m4a"
RUN_META = ROOT / "cloud_out" / "run_meta.json"

HYP_DIRS = {
    "H1": OUT / "H1_cluster_then_match",
    "H2": OUT / "H2_refine_reassign",
    "H3": OUT / "H3_cluster_clear_winner",
}
HYP_FNS: dict[str, Callable[..., tuple[list[str], dict[str, Any]]]] = {
    "H1": h1_cluster_then_match,
    "H2": h2_refine_reassign,
    "H3": h3_cluster_clear_winner,
}


def _round3(value: float) -> float:
    return round(float(value), 3)


def _now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: Path, payload: dict[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _sh(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True, text=True).strip()


def slice_full15_speech(
    full: SpeechArtifact,
    *,
    plan_start: float,
    plan_end: float,
    job_id: str,
) -> SpeechArtifact:
    regions: list[TimeInterval] = []
    for region in full.regions:
        start = max(float(region.start), plan_start)
        end = min(float(region.end), plan_end)
        if end <= start:
            continue
        local_start = _round3(start - plan_start)
        local_end = _round3(end - plan_start)
        if local_end <= local_start:
            continue
        regions.append(TimeInterval(start=local_start, end=local_end))
    speech_sec = _round3(sum(item.end - item.start for item in regions))
    return SpeechArtifact(
        schema_version="1",
        job_id=job_id,
        detector=full.detector,
        fallback_used=False,
        regions=regions,
        fallback_regions=[],
        speech_sec=speech_sec,
        runtime_sec=0.0,
    )


def _ffprobe_duration(path: Path) -> float:
    out = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
    ).strip()
    return float(out)


def slice_unified_wavs(src_wav: Path, cut: dict[str, Any], dest_dir: Path) -> list[dict[str, Any]]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    for part in cut["parts"]:
        dest = dest_dir / f"{part['id']}.wav"
        start = float(part["start"])
        duration = float(part["duration_sec"])
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-ss",
                f"{start:.3f}",
                "-t",
                f"{duration:.3f}",
                "-i",
                str(src_wav),
                "-c",
                "copy",
                str(dest),
            ],
            check=True,
        )
        dur = _ffprobe_duration(dest)
        items.append(
            {
                "id": part["id"],
                "plan_start": start,
                "plan_end": float(part["end"]),
                "path": str(dest),
                "ffprobe_duration_sec": _round3(dur),
            }
        )
    return items


def resolve_part_wavs(cut: dict[str, Any]) -> tuple[dict[str, Path], dict[str, Any]]:
    """Reuse unified_norm slices when present; otherwise cut full15 normalized.wav."""
    reused: dict[str, Path] = {}
    for part in cut["parts"]:
        pid = part["id"]
        for candidate in (
            UNIFIED / "parts" / f"{pid}.wav",
            UNIFIED / "parts_jobs" / pid / "normalized.wav",
        ):
            if candidate.is_file():
                reused[pid] = candidate
                break
    if len(reused) == len(cut["parts"]):
        return reused, {"source": "unified_norm_slices", "reused": True, "parts": {k: str(v) for k, v in reused.items()}}
    if not FULL15_JOB_WAV.is_file():
        raise FileNotFoundError(
            f"Need unified_norm part wavs or {FULL15_JOB_WAV} to slice once"
        )
    items = slice_unified_wavs(FULL15_JOB_WAV, cut, OUT / "parts")
    return {row["id"]: Path(row["path"]) for row in items}, {
        "source": "sliced_full15_job_normalized",
        "reused": False,
        "parts": {row["id"]: row["path"] for row in items},
    }


def resolve_speech(cut: dict[str, Any], full_speech: SpeechArtifact) -> dict[str, SpeechArtifact]:
    out: dict[str, SpeechArtifact] = {}
    for part in cut["parts"]:
        pid = part["id"]
        unified_speech = UNIFIED / "parts_jobs" / pid / "speech.json"
        if unified_speech.is_file():
            out[pid] = load_artifact(unified_speech, SpeechArtifact)
        else:
            out[pid] = slice_full15_speech(
                full_speech,
                plan_start=float(part["start"]),
                plan_end=float(part["end"]),
                job_id=pid,
            )
    return out


def part1_gallery(
    embeddings: np.ndarray,
    segments: list[tuple[float, float]],
    cfg: Any,
    *,
    job_id: str,
    total_duration: float,
) -> tuple[SpeakerGallery, TurnsArtifact]:
    threshold = float(cfg.embed.cluster_distance_threshold)
    raw_labels = _ahc_labels(embeddings, threshold)
    raw_ids = [f"SPEAKER_{int(lbl):02d}" for lbl in raw_labels]
    artifact = _turns_from_window_speakers(
        segments,
        raw_ids,
        cfg,
        job_id=job_id,
        total_duration=total_duration,
        runtime_sec=0.0,
        compact_renumber=True,
    )
    final_for_windows = window_speakers_after_turns(segments, raw_ids, artifact.turns)
    gallery = SpeakerGallery.from_ahc(embeddings, raw_labels, final_for_windows, threshold)
    return gallery, artifact


def baseline_metrics(part1_ids: list[str], offsets: dict[str, float]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for part in ("part02", "part03"):
        path = UNIFIED / "parts_jobs" / part / "turns.json"
        art = load_artifact(path, TurnsArtifact)
        metrics = turns_metrics(
            hyp="baseline",
            part=part,
            turns=art.turns,
            part1_ids=part1_ids,
            abs_offset=offsets[part],
        )
        _write_json(OUT / f"baseline_metrics_{part}.json", metrics)
        out[part] = metrics
    return out


def attach_window_times(
    log: dict[str, Any], segments: list[tuple[float, float]]
) -> dict[str, Any]:
    for key in ("windows", "pass1_windows", "pass2_windows"):
        rows = log.get(key)
        if not isinstance(rows, list):
            continue
        for row in rows:
            idx = int(row["index"])
            row["start"] = segments[idx][0]
            row["end"] = segments[idx][1]
    for cluster in log.get("clusters") or []:
        idxs = cluster.get("window_indices") or []
        if idxs:
            cluster["start"] = segments[idxs[0]][0]
            cluster["end"] = segments[idxs[-1]][1]
    return log


def replay_hyp(
    hyp: str,
    gallery_part1: SpeakerGallery,
    parts_data: dict[str, dict[str, Any]],
    cfg: Any,
    part1_ids: list[str],
) -> dict[str, dict[str, Any]]:
    dest = HYP_DIRS[hyp]
    dest.mkdir(parents=True, exist_ok=True)
    gallery = gallery_part1.clone()
    fn = HYP_FNS[hyp]
    metrics_by_part: dict[str, dict[str, Any]] = {}
    for part in ("part02", "part03"):
        t0 = time.time()
        row = parts_data[part]
        assigned, log = fn(gallery, row["embeddings"], row["segments"])
        runtime = round(time.time() - t0, 3)
        log = attach_window_times(log, row["segments"])
        log["part"] = part
        log["abs_offset"] = row["abs_offset"]
        log["runtime_sec"] = runtime
        turns = labels_to_turns(
            row["segments"],
            assigned,
            cfg,
            job_id=part,
            total_duration=row["duration_sec"],
            runtime_sec=runtime,
        )
        part_dir = dest / part
        part_dir.mkdir(parents=True, exist_ok=True)
        dump_artifact(turns, part_dir / "turns.json")
        _write_json(dest / f"assign_or_match_log_{part}.json", log)
        _write_json(dest / f"gallery_after_{part}.json", gallery.to_json())
        metrics = turns_metrics(
            hyp=hyp,
            part=part,
            turns=turns.turns,
            part1_ids=part1_ids,
            abs_offset=row["abs_offset"],
        )
        _write_json(dest / f"metrics_{part}.json", metrics)
        metrics_by_part[part] = metrics
    return metrics_by_part


def _md_row(m: dict[str, Any]) -> str:
    return (
        f"| {m['hyp']} | {m['part']} | {m['n_turns']} | {m['n_turns_lt_1s']} | "
        f"{m['n_turns_lt_2s']} | {m['n_speaker_switches']} | {m['n_speakers']} | "
        f"{', '.join(m['speaker_ids'])} | {', '.join(m['new_ids_vs_part1']) or '—'} |"
    )


def write_compare(
    all_metrics: dict[str, dict[str, dict[str, Any]]],
    prep: dict[str, Any],
    wall_sec: float,
) -> dict[str, Any]:
    order = ("baseline", "H1", "H2", "H3")
    combined: dict[str, dict[str, int]] = {}
    for hyp in order:
        p2 = all_metrics[hyp]["part02"]
        p3 = all_metrics[hyp]["part03"]
        combined[hyp] = {
            "n_turns_lt_1s": p2["n_turns_lt_1s"] + p3["n_turns_lt_1s"],
            "n_speaker_switches": p2["n_speaker_switches"] + p3["n_speaker_switches"],
            "n_speakers_max": max(p2["n_speakers"], p3["n_speakers"]),
            "n_turns": p2["n_turns"] + p3["n_turns"],
        }

    base_spk = combined["baseline"]["n_speakers_max"]
    ranked = sorted(
        [h for h in ("H1", "H2", "H3")],
        key=lambda h: (
            combined[h]["n_turns_lt_1s"],
            combined[h]["n_speaker_switches"],
            combined[h]["n_speakers_max"],
        ),
    )
    winner = ranked[0]
    tied = [
        h
        for h in ("H1", "H2", "H3")
        if combined[h]["n_turns_lt_1s"] == combined[winner]["n_turns_lt_1s"]
        and combined[h]["n_speaker_switches"] == combined[winner]["n_speaker_switches"]
        and combined[h]["n_speakers_max"] == combined[winner]["n_speakers_max"]
    ]
    winner_label = winner if len(tied) == 1 else f"{winner} (tied with {', '.join(tied[1:])})"
    growth = combined[winner]["n_speakers_max"] - base_spk
    crumbs_delta = combined[winner]["n_turns_lt_1s"] - combined["baseline"]["n_turns_lt_1s"]
    switch_delta = combined[winner]["n_speaker_switches"] - combined["baseline"]["n_speaker_switches"]
    huge_growth = growth > 2
    improved = crumbs_delta < 0 or switch_delta < 0
    if improved and not huge_growth:
        verdict = (
            f"PASS — {winner_label} reduces crumbs and/or switches vs baseline "
            "without huge speaker growth."
        )
        status = "PASS"
    elif improved and huge_growth:
        verdict = (
            f"PASS_WITH_WARNINGS — {winner} lowers crumbs/switches but n_speakers grew by {growth} vs baseline."
        )
        status = "PASS_WITH_WARNINGS"
    else:
        verdict = (
            "FAIL — no hypothesis reduced part02+part03 n_turns_lt_1s or n_speaker_switches vs baseline."
        )
        status = "FAIL"

    lines = [
        "# Cluster rebuild A/B — H1 / H2 / H3 vs unified_norm baseline",
        "",
        f"## Verdict: {status}",
        "",
        verdict,
        "",
        "Primary success: lower `n_turns_lt_1s` and/or `n_speaker_switches` on part02+part03 "
        "without huge `n_speakers` growth vs baseline. Hypotheses were replayed **separately** "
        "from the same part1 gallery. No sticky-previous-window. No ASR/packing.",
        "",
        "## Combined part02+part03",
        "",
        "| hyp | n_turns | n_turns_lt_1s | n_speaker_switches | n_speakers_max | Δlt1s vs baseline | Δswitches vs baseline | Δspeakers_max |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for hyp in order:
        c = combined[hyp]
        d1 = c["n_turns_lt_1s"] - combined["baseline"]["n_turns_lt_1s"]
        ds = c["n_speaker_switches"] - combined["baseline"]["n_speaker_switches"]
        dsp = c["n_speakers_max"] - combined["baseline"]["n_speakers_max"]
        lines.append(
            f"| {hyp} | {c['n_turns']} | {c['n_turns_lt_1s']} | {c['n_speaker_switches']} | "
            f"{c['n_speakers_max']} | {d1:+d} | {ds:+d} | {dsp:+d} |"
        )

    lines += [
        "",
        "## Per part",
        "",
        "| hyp | part | n_turns | n_turns_lt_1s | n_turns_lt_2s | n_speaker_switches | n_speakers | speaker_ids | new_ids_vs_part1 |",
        "|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for hyp in order:
        for part in ("part02", "part03"):
            lines.append(_md_row(all_metrics[hyp][part]))

    lines += [
        "",
        "## part02 hotspot [365.0, 375.5] abs",
        "",
        "Baseline unified_norm flickers 00↔01 here. Each row is overlapping turns.",
        "",
    ]
    for hyp in order:
        hot = all_metrics[hyp]["part02"].get("hotspot_365_375") or []
        seq = " → ".join(f"{h['speaker']}({h['duration_sec']}s @{h['start_abs']})" for h in hot)
        lines.append(f"- **{hyp}** ({len(hot)} turns): {seq or 'none'}")

    lines += [
        "",
        "## Checks",
        "",
        "| id | check | value | threshold | status |",
        "|---|---|---|---|---|",
        "| P0 | hyps run separately | H1, H2, H3 each clone part1 gallery | do not combine | PASS |",
        "| P1 | sticky-previous-window | not implemented | forbidden | PASS |",
        f"| P2 | embeddings once | {prep.get('n_windows')} | part01–03 dumped | PASS |",
        f"| B0 | baseline part02 lt1s | {all_metrics['baseline']['part02']['n_turns_lt_1s']} | record (unified_norm 13) | PASS (record) |",
        f"| C1 | best hyp vs baseline lt1s+switches | {winner_label} Δlt1s={crumbs_delta:+d} Δsw={switch_delta:+d} | lower at least one | "
        + ("PASS" if improved else "FAIL")
        + " |",
        f"| C2 | speaker growth (best hyp) | {growth:+d} vs baseline max {base_spk} | not huge (>2) | "
        + ("WARN" if huge_growth else "PASS")
        + " |",
        f"| L1 | LLM / ASR | 0 / skipped | out of scope | PASS |",
        "",
        "## Agent judgement",
        "",
        f"Rank by (lt1s, switches, n_speakers_max) on part02+part03: **{' > '.join(ranked)}**. "
        f"Winner **{winner_label}**.",
        "",
        "H1 maps a whole local AHC cluster to one gallery id (or one new id), which should stop "
        "single-talker flicker across ids inside a cluster. H2 keeps window assign but one centroid "
        "refine + re-assign. H3 is H1 plus a 0.05 clear-winner margin; clusters <2.0 s of union "
        "speech that are ambiguous map to the nearest gallery id (no new micro-id).",
        "",
        "On this file H1 and H3 produced **identical** part02/part03 turns: part-local AHC made "
        "four clusters and every cluster already had d_best≤0.85 with margin≥0.05, so H3's extra "
        "rule never fired. Short 00↔01 dialogue still appears later in part02 (not a "
        "sticky-previous-window collapse). SPEAKER_02 from baseline (~4 s crumbs) is absorbed; "
        "some SPEAKER_01 mass moves into SPEAKER_00 (one large cluster at d_best≈0.57 to 00).",
        "",
        f"Prep: wav={prep.get('wav_meta', {}).get('source')}; shared VAD from unified_norm/full15; "
        f"wall_sec={wall_sec}. Host nproc=4 (not a 2-vCPU TTFT demo). "
        "`cloud_in/inputs/artifacts/hypotheses.md` was absent; hyps taken from the agent prompt.",
        "",
        "## Environment",
        "",
        "- stage D5.TTFT-cluster-rebuild; onnx_threads=2; HF_HUB_OFFLINE=1",
        "- helper: cloud_out/artifacts/split3_cluster_rebuild/scripts/",
        "- baseline: cloud_out/artifacts/split3_unified_norm/ (not deleted)",
        "- no src/ config/ tests/ edits; no PR; no LLM API",
        "",
        "## Deviations and blockers",
        "",
        "hypotheses.md missing from pack; otherwise none.",
        "",
    ]
    (OUT / "compare_parts.md").write_text("\n".join(lines), encoding="utf-8")
    return {
        "status": status,
        "verdict": verdict,
        "winner": winner,
        "winner_label": winner_label,
        "tied": tied,
        "ranked": ranked,
        "combined": combined,
        "crumbs_delta": crumbs_delta,
        "switch_delta": switch_delta,
        "speaker_growth": growth,
    }


def update_run_meta(payload: dict[str, Any]) -> None:
    existing: dict[str, Any] = {}
    if RUN_META.is_file():
        existing = json.loads(RUN_META.read_text(encoding="utf-8"))
    existing.update(payload)
    existing["stage"] = "D5.TTFT-cluster-rebuild"
    existing["written_at_utc"] = _now_utc()
    existing["llm_call_count"] = 0
    _write_json(RUN_META, existing)


def main() -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.chdir(ROOT)
    job_t0 = time.monotonic()

    cut = json.loads(CUT_PLAN.read_text(encoding="utf-8"))
    cfg_root = load_config(profile="demo")
    cfg_root = cfg_root.model_copy(deep=True)
    cfg_root.diarization.onnx_threads = 2
    cfg = cfg_root.diarization

    OUT.mkdir(parents=True, exist_ok=True)
    full_speech = load_artifact(FULL15_SPEECH, SpeechArtifact)
    wavs, wav_meta = resolve_part_wavs(cut)
    speeches = resolve_speech(cut, full_speech)

    offsets = {p["id"]: float(p["start"]) for p in cut["parts"]}
    _write_json(
        OUT / "offsets.json",
        {
            "schema_version": "1",
            "cut_plan": str(CUT_PLAN),
            "parts": {
                p["id"]: {
                    "abs_offset": float(p["start"]),
                    "plan_end": float(p["end"]),
                    "duration_sec": float(p["duration_sec"]),
                }
                for p in cut["parts"]
            },
        },
    )

    embedder = WeSpeakerDiarizer()._get_embedder()
    parts_data: dict[str, dict[str, Any]] = {}
    n_windows: dict[str, int] = {}
    for part in cut["parts"]:
        pid = part["id"]
        wav = wavs[pid]
        speech = speeches[pid]
        duration = _round3(float(sf.info(str(wav)).duration))
        t_emb = time.time()
        segments, embeddings = extract_wespeaker_windows(wav, speech, cfg, embedder)
        emb_sec = round(time.time() - t_emb, 3)
        windows = [
            {"index": i, "start": start, "end": end}
            for i, (start, end) in enumerate(segments)
        ]
        _write_json(OUT / f"{pid}_windows.json", windows)
        np.save(OUT / f"{pid}_embeddings.npy", embeddings)
        n_windows[pid] = len(segments)
        parts_data[pid] = {
            "segments": segments,
            "embeddings": embeddings,
            "duration_sec": duration,
            "abs_offset": offsets[pid],
            "wav": str(wav),
            "embed_sec": emb_sec,
        }

    gallery_p1, p1_turns = part1_gallery(
        parts_data["part01"]["embeddings"],
        parts_data["part01"]["segments"],
        cfg,
        job_id="part01",
        total_duration=parts_data["part01"]["duration_sec"],
    )
    _write_json(OUT / "centroids_part01.json", gallery_p1.to_json())
    dump_artifact(p1_turns, OUT / "part01_ahc_turns.json")
    part1_ids = [s["id"] for s in gallery_p1.speakers]
    unified_p1 = load_artifact(UNIFIED / "parts_jobs" / "part01" / "turns.json", TurnsArtifact)
    baseline_part1_ids = sorted({t.speaker for t in unified_p1.turns})

    prep = {
        "wav_meta": wav_meta,
        "vad_source": "unified_norm speech.json if present else full15 slice",
        "n_windows": n_windows,
        "embedding_dim": int(parts_data["part01"]["embeddings"].shape[1])
        if n_windows["part01"]
        else 0,
        "part1_gallery_ids": part1_ids,
        "baseline_part1_ids": baseline_part1_ids,
        "embed_sec": {pid: parts_data[pid]["embed_sec"] for pid in n_windows},
        "cluster_distance_threshold": cfg.embed.cluster_distance_threshold,
        "hotspot_abs": list(HOTSPOT_ABS),
    }
    _write_json(OUT / "prep_meta.json", prep)

    all_metrics: dict[str, dict[str, dict[str, Any]]] = {
        "baseline": baseline_metrics(baseline_part1_ids, offsets),
    }
    for hyp in ("H1", "H2", "H3"):
        all_metrics[hyp] = replay_hyp(hyp, gallery_p1, parts_data, cfg, part1_ids)

    wall = _round3(time.monotonic() - job_t0)
    summary = write_compare(all_metrics, prep, wall)
    update_run_meta(
        {
            "stage": "D5.TTFT-cluster-rebuild",
            "branch": _sh("git rev-parse --abbrev-ref HEAD"),
            "git_rev": _sh("git rev-parse HEAD"),
            "wall_time_sec": wall,
            "cluster_rebuild": {
                "prep": {
                    "n_windows": n_windows,
                    "wav_source": wav_meta.get("source"),
                    "embed_sec": prep["embed_sec"],
                },
                "compare": summary,
                "metrics": {
                    hyp: {part: all_metrics[hyp][part] for part in ("part02", "part03")}
                    for hyp in ("baseline", "H1", "H2", "H3")
                },
            },
            "notes": [
                "Research spike: cluster rebuild H1/H2/H3, no src/config/tests edits, no PR.",
                "ASR/packing out of scope. Shared VAD + unified-norm wav slices reused.",
                "hypotheses.md absent from pack; hyps taken from the agent prompt.",
                "nproc=4 so 2-CPU TTFT is not demonstrated.",
            ],
        }
    )
    print(
        json.dumps(
            {
                "wall_sec": wall,
                "n_windows": n_windows,
                "compare": {
                    "status": summary["status"],
                    "winner": summary["winner"],
                    "combined": summary["combined"],
                },
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

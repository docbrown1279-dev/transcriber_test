#!/usr/bin/env python3
"""Measure pre-normalization RMS for sampled transcript fragments."""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from array import array
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


SAMPLE_RATE = 16_000


def decode_mono_f32(audio_path: Path) -> array:
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
        "-f",
        "f32le",
        "pipe:1",
    ]
    completed = subprocess.run(command, check=True, capture_output=True)
    samples = array("f")
    samples.frombytes(completed.stdout)
    return samples


def rms_dbfs(samples: array, start: float, end: float) -> tuple[float, int]:
    first = max(0, round(start * SAMPLE_RATE))
    last = min(len(samples), round(end * SAMPLE_RATE))
    if last <= first:
        raise ValueError(f"Empty interval: {start:.3f}-{end:.3f}")
    count = last - first
    mean_square = math.fsum(value * value for value in samples[first:last]) / count
    if mean_square == 0:
        return -math.inf, count
    return 20 * math.log10(math.sqrt(mean_square)), count


def pearson(values_x: list[float], values_y: list[float]) -> float | None:
    if len(values_x) < 2:
        return None
    mean_x = statistics.fmean(values_x)
    mean_y = statistics.fmean(values_y)
    centered_x = [value - mean_x for value in values_x]
    centered_y = [value - mean_y for value in values_y]
    denominator = math.sqrt(
        math.fsum(value * value for value in centered_x)
        * math.fsum(value * value for value in centered_y)
    )
    if denominator == 0:
        return None
    return math.fsum(
        x_value * y_value
        for x_value, y_value in zip(centered_x, centered_y, strict=True)
    ) / denominator


def rounded(value: float | None) -> float | None:
    return None if value is None else round(value, 3)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("meaning_check", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    meaning = json.loads(args.meaning_check.read_text(encoding="utf-8"))
    samples_by_id = {item["id"]: item for item in meaning["samples"]}
    verdicts_by_id = {
        item["id"]: item["verdict"]
        for item in meaning["assessment"]["assessments"]
    }
    audio = decode_mono_f32(args.audio)

    fragment_results = []
    per_speaker: dict[str, list[dict]] = defaultdict(list)
    for fragment_id, fragment in samples_by_id.items():
        level, sample_count = rms_dbfs(
            audio,
            fragment["start"],
            fragment["end"],
        )
        result = {
            "id": fragment_id,
            "speaker": fragment["speaker"],
            "start": fragment["start"],
            "end": fragment["end"],
            "duration_sec": round(fragment["end"] - fragment["start"], 3),
            "rms_dbfs": round(level, 3),
            "pcm_sample_count": sample_count,
            "meaning_verdict": verdicts_by_id[fragment_id],
        }
        fragment_results.append(result)
        per_speaker[fragment["speaker"]].append(result)

    speaker_results = []
    for speaker, fragments in sorted(per_speaker.items()):
        levels = [item["rms_dbfs"] for item in fragments]
        coherent_count = sum(
            item["meaning_verdict"] == "coherent" for item in fragments
        )
        speaker_results.append(
            {
                "speaker": speaker,
                "fragment_count": len(fragments),
                "rms_dbfs_mean": round(statistics.fmean(levels), 3),
                "rms_dbfs_median": round(statistics.median(levels), 3),
                "rms_dbfs_min": round(min(levels), 3),
                "rms_dbfs_max": round(max(levels), 3),
                "coherent_count": coherent_count,
                "coherent_ratio": round(coherent_count / len(fragments), 3),
            }
        )

    coherent_levels = [
        item["rms_dbfs"]
        for item in fragment_results
        if item["meaning_verdict"] == "coherent"
    ]
    incoherent_levels = [
        item["rms_dbfs"]
        for item in fragment_results
        if item["meaning_verdict"] == "incoherent"
    ]
    fragment_correlation = pearson(
        [item["rms_dbfs"] for item in fragment_results],
        [
            1.0 if item["meaning_verdict"] == "coherent" else 0.0
            for item in fragment_results
        ],
    )
    speaker_correlation = pearson(
        [item["rms_dbfs_mean"] for item in speaker_results],
        [item["coherent_ratio"] for item in speaker_results],
    )
    coherent_mean = (
        statistics.fmean(coherent_levels) if coherent_levels else None
    )
    incoherent_mean = (
        statistics.fmean(incoherent_levels) if incoherent_levels else None
    )
    difference = (
        coherent_mean - incoherent_mean
        if coherent_mean is not None and incoherent_mean is not None
        else None
    )

    output = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "audio_artifact": str(args.audio),
        "audio_stage": "original_pre_loudnorm",
        "meaning_check_artifact": str(args.meaning_check),
        "sample_rate_hz": SAMPLE_RATE,
        "metric": "whole-fragment RMS dBFS after mono decode; no gating",
        "fragments": fragment_results,
        "speakers": speaker_results,
        "comparison": {
            "coherent_fragment_count": len(coherent_levels),
            "incoherent_fragment_count": len(incoherent_levels),
            "coherent_rms_dbfs_mean": rounded(coherent_mean),
            "incoherent_rms_dbfs_mean": rounded(incoherent_mean),
            "coherent_minus_incoherent_db": rounded(difference),
            "fragment_point_biserial_correlation": rounded(
                fragment_correlation
            ),
            "speaker_mean_rms_vs_coherent_ratio_correlation": rounded(
                speaker_correlation
            ),
        },
        "limitations": [
            "Только 12 фрагментов: 3 на спикера.",
            "Связными признаны только 2 фрагмента, оба одного спикера.",
            "RMS включает паузы и шум внутри границ ASR-сегмента.",
            "Корреляция не доказывает причинность и не отделяет SNR от громкости.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

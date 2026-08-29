#!/usr/bin/env python3
"""Run the bounded Stage 1e diarization and ASR experiment."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "asr" / "eval_clips"
EXTRACTS = OUT / "_extracts"
CLIPS = [
    ("test_voice", ROOT / "data/test_voice.m4a", 83.0),
    ("test_apartments", ROOT / "data/test_apartments.m4a", 85.0),
    ("test_transformers", ROOT / "data/test_transformers.m4a", 85.0),
    ("test_ninth", ROOT / "data/test_ninth.m4a", 85.0),
]
SAMPLE_RATE = 16_000


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def run(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )


def merge_turns(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge close same-speaker turns, then absorb sub-second turns."""
    rows: list[dict[str, Any]] = []
    for turn in sorted(raw, key=lambda item: (item["start"], item["end"])):
        current = {"start": float(turn["start"]), "end": float(turn["end"]), "speaker": turn["speaker"]}
        if (
            rows
            and current["speaker"] == rows[-1]["speaker"]
            and current["start"] - rows[-1]["end"] <= 0.3 + 1e-9
        ):
            rows[-1]["start"] = min(rows[-1]["start"], current["start"])
            rows[-1]["end"] = max(rows[-1]["end"], current["end"])
        else:
            rows.append(current)

    while len(rows) > 1:
        short_index = next(
            (index for index, row in enumerate(rows) if row["end"] - row["start"] < 1.0 - 1e-9),
            None,
        )
        if short_index is None:
            break
        row = rows[short_index]
        candidates: list[tuple[int, float, float, int]] = []
        for neighbor_index in (short_index - 1, short_index + 1):
            if 0 <= neighbor_index < len(rows):
                neighbor = rows[neighbor_index]
                gap = max(
                    0.0,
                    max(row["start"], neighbor["start"]) - min(row["end"], neighbor["end"]),
                )
                same_penalty = 0 if neighbor["speaker"] == row["speaker"] else 1
                candidates.append((same_penalty, gap, -(neighbor["end"] - neighbor["start"]), neighbor_index))
        _, _, _, neighbor_index = min(candidates)
        neighbor = rows[neighbor_index]
        combined = {
            "start": min(row["start"], neighbor["start"]),
            "end": max(row["end"], neighbor["end"]),
            "speaker": (
                row["speaker"]
                if row["speaker"] == neighbor["speaker"]
                else max((row, neighbor), key=lambda item: item["end"] - item["start"])["speaker"]
            ),
        }
        first = min(short_index, neighbor_index)
        second = max(short_index, neighbor_index)
        rows[first] = combined
        rows.pop(second)

        # Absorption can make a same-speaker boundary newly eligible.
        compacted: list[dict[str, Any]] = []
        for item in rows:
            if (
                compacted
                and item["speaker"] == compacted[-1]["speaker"]
                and item["start"] - compacted[-1]["end"] <= 0.3 + 1e-9
            ):
                compacted[-1]["start"] = min(compacted[-1]["start"], item["start"])
                compacted[-1]["end"] = max(compacted[-1]["end"], item["end"])
            else:
                compacted.append(item)
        rows = compacted
    return rows


def holes(rows: list[dict[str, Any]], duration: float) -> list[dict[str, float]]:
    union: list[list[float]] = []
    for row in sorted(rows, key=lambda item: item["start"]):
        start = max(0.0, float(row["start"]))
        end = min(duration, float(row["end"]))
        if union and start <= union[-1][1]:
            union[-1][1] = max(union[-1][1], end)
        else:
            union.append([start, end])
    result = []
    cursor = 0.0
    for start, end in union:
        if start - cursor >= 0.5:
            result.append({"start": round(cursor, 6), "end": round(start, 6)})
        cursor = max(cursor, end)
    if duration - cursor >= 0.5:
        result.append({"start": round(cursor, 6), "end": round(duration, 6)})
    return result


def astats(path: Path) -> tuple[float, float]:
    process = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            str(path),
            "-af",
            "astats=metadata=0:reset=0",
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )
    overall = process.stderr.rsplit("Overall", 1)[-1]

    def value(label: str) -> float:
        match = re.search(rf"{re.escape(label)}:\s*(-?inf|[-+]?\d+(?:\.\d+)?)", overall, re.I)
        if not match:
            raise RuntimeError(f"Missing {label} in astats output for {path}")
        return float("-inf") if match.group(1).lower() == "-inf" else float(match.group(1))

    return value("RMS level dB"), value("Peak level dB")


def extract(source: Path, start: float, end: float, destination: Path, gain_db: float = 0.0) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-ss",
        f"{start:.9f}",
        "-to",
        f"{end:.9f}",
        "-i",
        str(source),
        "-map",
        "0:a:0",
        "-ac",
        "1",
        "-ar",
        str(SAMPLE_RATE),
    ]
    if gain_db > 0:
        command += ["-af", f"volume={gain_db:.6f}dB"]
    command += ["-c:a", "pcm_s16le", str(destination)]
    run(command)
    import soundfile as sf

    info = sf.info(destination)
    expected = round((end - start) * SAMPLE_RATE)
    if abs(info.frames - expected) > 2:
        raise RuntimeError(
            f"Duration mismatch for {destination}: {info.frames} frames, expected {expected}"
        )


def prepare() -> None:
    from pyannote.audio import Pipeline

    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        raise RuntimeError("HF token is missing")
    started = time.monotonic()
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1",
        use_auth_token=token,
    )
    pipeline.to(__import__("torch").device("cpu"))
    model_name = "pyannote/speaker-diarization-3.1"
    for clip_id, audio, duration in CLIPS:
        clip_started = time.monotonic()
        result = pipeline(str(audio))
        annotation = result.get("speaker_diarization", result) if isinstance(result, dict) else result
        raw = [
            {
                "start": round(float(segment.start), 6),
                "end": round(float(segment.end), 6),
                "speaker": str(speaker),
            }
            for segment, _, speaker in annotation.itertracks(yield_label=True)
        ]
        merged = merge_turns(raw)
        clip_dir = EXTRACTS / clip_id
        for index, row in enumerate(merged):
            raw_wav = clip_dir / f"turn_{index:03d}_raw.wav"
            gained_wav = clip_dir / f"turn_{index:03d}_linear.wav"
            extract(audio, row["start"], row["end"], raw_wav)
            rms, peak = astats(raw_wav)
            gain = 0.0
            if rms < -30.0 and peak < 0.0 and math.isfinite(rms):
                gain = min(-23.0 - rms, 18.0, -1.0 - peak)
                gain = max(0.0, gain)
            extract(audio, row["start"], row["end"], gained_wav, gain)
            row.update(
                {
                    "id": index,
                    "rms_dbfs": round(rms, 3) if math.isfinite(rms) else None,
                    "peak_dbfs": round(peak, 3) if math.isfinite(peak) else None,
                    "gain_db": round(gain, 3),
                    "raw_wav": str(raw_wav.relative_to(ROOT)),
                    "gained_wav": str(gained_wav.relative_to(ROOT)),
                }
            )
        payload = {
            "audio": str(audio.relative_to(ROOT)),
            "duration_sec": duration,
            "model": model_name,
            "provider": "pyannote.audio",
            "execution_mode": "local",
            "runtime_sec": round(time.monotonic() - clip_started, 3),
            "raw_turns": raw,
            "merged_turns": merged,
            "holes_ge_0_5_sec": holes(merged, duration),
        }
        write_json(OUT / "pyannote" / f"{clip_id}.json", payload)
    write_json(
        OUT / "pyannote" / "_run.json",
        {"model": model_name, "runtime_sec": round(time.monotonic() - started, 3)},
    )


def load_prepared(clip_id: str) -> dict[str, Any]:
    return json.loads((OUT / "pyannote" / f"{clip_id}.json").read_text(encoding="utf-8"))


def segments_for_gigaam(clip_id: str, *, gained: bool) -> list[dict[str, Any]]:
    prepared = load_prepared(clip_id)
    audio = ROOT / prepared["audio"]
    pieces = []
    for row in prepared["merged_turns"]:
        piece_start = row["start"]
        piece_number = 0
        while piece_start < row["end"] - 1e-9:
            piece_end = min(piece_start + 25.0, row["end"])
            suffix = "linear" if gained else "raw"
            path = EXTRACTS / clip_id / f"turn_{row['id']:03d}_piece_{piece_number:02d}_{suffix}.wav"
            extract(audio, piece_start, piece_end, path, row["gain_db"] if gained else 0.0)
            pieces.append(
                {
                    "start": piece_start,
                    "end": piece_end,
                    "speaker": row["speaker"],
                    "path": path,
                }
            )
            piece_start = piece_end
            piece_number += 1
    return pieces


def hypothesis(
    clip_id: str,
    model: str,
    provider: str,
    runtime_sec: float,
    segments: list[dict[str, Any]],
    gain: str,
) -> dict[str, Any]:
    prepared = load_prepared(clip_id)
    return {
        "audio": prepared["audio"],
        "language": "ru",
        "duration_sec": prepared["duration_sec"],
        "model": model,
        "provider": provider,
        "execution_mode": "local",
        "gain": gain,
        "runtime_sec": round(runtime_sec, 3),
        "segments": [
            {
                "id": index,
                "start": round(item["start"], 6),
                "end": round(item["end"], 6),
                "speaker": item["speaker"],
                "text": item["text"].strip(),
            }
            for index, item in enumerate(segments)
        ],
    }


def gigaam_pass(ungained: bool) -> None:
    import gigaam

    started = time.monotonic()
    selected = "v3_rnnt"
    try:
        model = gigaam.load_model(selected, fp16_encoder=False, device="cpu")
        label = "gigaam-v3-rnnt"
        output_id = "gigaam_v3"
    except Exception:
        selected = "v2_rnnt"
        model = gigaam.load_model(selected, fp16_encoder=False, device="cpu")
        label = "gigaam-v2-rnnt"
        output_id = "gigaam_v2"
    if ungained:
        output_id = "gigaam_v3_ungained" if selected == "v3_rnnt" else "gigaam_v2_ungained"
    for clip_id, _, _ in CLIPS:
        prepared = load_prepared(clip_id)
        if ungained and any(
            row["peak_dbfs"] is not None and row["peak_dbfs"] >= -0.1
            for row in prepared["merged_turns"]
        ):
            continue
        clip_started = time.monotonic()
        rows = segments_for_gigaam(clip_id, gained=not ungained)
        recognized = []
        for row in rows:
            text = model.transcribe(str(row["path"]))
            recognized.append({**row, "text": str(text)})
        write_json(
            OUT / output_id / f"{clip_id}.json",
            hypothesis(
                clip_id,
                label,
                "gigaam",
                time.monotonic() - clip_started,
                recognized,
                "none" if ungained else (
                    "linear" if any(row["gain_db"] > 0 for row in prepared["merged_turns"]) else "none"
                ),
            ),
        )
    write_json(
        OUT / output_id / "_run.json",
        {"model": selected, "runtime_sec": round(time.monotonic() - started, 3)},
    )
    del model
    gc.collect()


def transformer_pass(model_id: str, output_id: str) -> None:
    import soundfile as sf
    import torch
    from transformers import pipeline

    started = time.monotonic()
    asr = pipeline(
        "automatic-speech-recognition",
        model=model_id,
        device=-1,
        dtype=torch.float32,
    )
    for clip_id, _, _ in CLIPS:
        prepared = load_prepared(clip_id)
        clip_started = time.monotonic()
        recognized = []
        for row in prepared["merged_turns"]:
            samples, sample_rate = sf.read(ROOT / row["gained_wav"], dtype="float32")
            result = asr(
                {"array": samples, "sampling_rate": sample_rate},
                generate_kwargs={
                    "language": "ru",
                    "task": "transcribe",
                    "condition_on_prev_tokens": False,
                },
                return_timestamps=False,
            )
            recognized.append({**row, "text": result["text"]})
        write_json(
            OUT / output_id / f"{clip_id}.json",
            hypothesis(
                clip_id,
                model_id,
                "transformers",
                time.monotonic() - clip_started,
                recognized,
                "linear" if any(row["gain_db"] > 0 for row in prepared["merged_turns"]) else "none",
            ),
        )
    write_json(
        OUT / output_id / "_run.json",
        {"model": model_id, "runtime_sec": round(time.monotonic() - started, 3)},
    )
    del asr
    gc.collect()


def faster_whisper_pass() -> None:
    from faster_whisper import WhisperModel

    started = time.monotonic()
    model_id = "large-v3"
    model = WhisperModel(model_id, device="cpu", compute_type="int8")
    for clip_id, _, _ in CLIPS:
        prepared = load_prepared(clip_id)
        clip_started = time.monotonic()
        recognized = []
        for row in prepared["merged_turns"]:
            generated, _ = model.transcribe(
                str(ROOT / row["gained_wav"]),
                language="ru",
                vad_filter=False,
                condition_on_previous_text=False,
            )
            text = " ".join(segment.text.strip() for segment in generated).strip()
            recognized.append({**row, "text": text})
        write_json(
            OUT / "faster_whisper_large_v3" / f"{clip_id}.json",
            hypothesis(
                clip_id,
                model_id,
                "faster-whisper",
                time.monotonic() - clip_started,
                recognized,
                "linear" if any(row["gain_db"] > 0 for row in prepared["merged_turns"]) else "none",
            ),
        )
    write_json(
        OUT / "faster_whisper_large_v3" / "_run.json",
        {"model": model_id, "runtime_sec": round(time.monotonic() - started, 3)},
    )
    del model
    gc.collect()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "phase",
        choices=["prepare", "gigaam", "gigaam-ungained", "turbo", "faster", "large-ru"],
    )
    args = parser.parse_args()
    if args.phase == "prepare":
        prepare()
    elif args.phase == "gigaam":
        gigaam_pass(False)
    elif args.phase == "gigaam-ungained":
        gigaam_pass(True)
    elif args.phase == "turbo":
        transformer_pass("bond005/whisper-podlodka-turbo", "podlodka_turbo")
    elif args.phase == "faster":
        faster_whisper_pass()
    elif args.phase == "large-ru":
        transformer_pass("bond005/whisper-large-v3-ru-podlodka", "podlodka_large_v3_ru")


if __name__ == "__main__":
    main()

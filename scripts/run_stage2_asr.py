#!/usr/bin/env python3
"""Stage 2 full-meeting pyannote + linear gain + GigaAM v3_rnnt only."""

from __future__ import annotations

import argparse
import gc
import json
import math
import os
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_stage1e import SAMPLE_RATE, astats, holes, merge_turns, run, write_json

ROOT = Path(__file__).resolve().parents[1]
AUDIO = ROOT / "data" / "fixtures" / "meeting_sample.m4a"
FALLBACK_AUDIO = ROOT / "docs" / "Голос 002.m4a"
OUT = ROOT / "results" / "asr" / "2"
PYANNOTE_DIR = OUT / "pyannote"
EXTRACTS = OUT / "_extracts"
GIGAAM_DIR = OUT / "gigaam_v3_rnnt"
DURATION_SEC = 1468.601746
MODEL_LIMIT_SEC = 25.0
MAX_RETRIES = 3  # initial + 2 extra


def audio_path() -> Path:
    if AUDIO.exists():
        return AUDIO
    if FALLBACK_AUDIO.exists():
        return FALLBACK_AUDIO
    raise FileNotFoundError("meeting audio missing")


def clamp_turns(rows: list[dict[str, Any]], duration: float) -> list[dict[str, Any]]:
    clamped = []
    for row in rows:
        start = min(max(0.0, float(row["start"])), duration)
        end = min(max(start, float(row["end"])), duration)
        if end - start < 1e-3:
            continue
        item = dict(row)
        item["start"] = round(start, 6)
        item["end"] = round(end, 6)
        clamped.append(item)
    return clamped


def extract_stage2(
    source: Path,
    start: float,
    end: float,
    destination: Path,
    gain_db: float = 0.0,
    file_duration: float | None = None,
) -> None:
    """Cut from the original file. Clamp to file end; pad/trim ffmpeg rounding only."""
    import numpy as np
    import soundfile as sf

    destination.parent.mkdir(parents=True, exist_ok=True)
    if file_duration is not None:
        end = min(end, file_duration)
        start = min(max(0.0, start), end)
    if end - start < 1e-3:
        raise RuntimeError(f"Empty extract window for {destination}")
    expected = max(1, round((end - start) * SAMPLE_RATE))
    duration = end - start

    def ffmpeg_cut(input_seek: bool) -> int:
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y"]
        if input_seek:
            command += ["-ss", f"{start:.9f}", "-to", f"{end:.9f}", "-i", str(source)]
        else:
            command += ["-i", str(source), "-ss", f"{start:.9f}", "-t", f"{duration:.9f}"]
        command += ["-map", "0:a:0", "-ac", "1", "-ar", str(SAMPLE_RATE)]
        if gain_db > 0:
            command += ["-af", f"volume={gain_db:.6f}dB"]
        command += ["-c:a", "pcm_s16le", str(destination)]
        run(command)
        return sf.info(destination).frames

    frames = ffmpeg_cut(True)
    if abs(frames - expected) > 2:
        frames = ffmpeg_cut(False)
    if abs(frames - expected) > 2:
        data, rate = sf.read(str(destination), dtype="float32")
        if data.ndim > 1:
            data = data[:, 0]
        if len(data) > expected:
            data = data[:expected]
        elif len(data) < expected:
            data = np.pad(data, (0, expected - len(data)))
        sf.write(str(destination), data, rate, subtype="PCM_16")
        frames = sf.info(destination).frames
    if abs(frames - expected) > 2:
        raise RuntimeError(
            f"Duration mismatch for {destination}: {frames} frames, expected {expected}"
        )


def load_token() -> str:
    token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if not token:
        raise RuntimeError("HF token is missing")
    return token


def waveform_from_original(path: Path) -> dict[str, Any]:
    """Decode the original file with ffmpeg only — no loudnorm, gain, or denoise."""
    import numpy as np
    import torch

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=sample_rate,channels",
            "-of",
            "csv=p=0",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    rate_s, channels_s = probe.stdout.strip().split(",")
    sample_rate = int(rate_s)
    channels = int(channels_s)
    raw = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(path),
            "-map",
            "0:a:0",
            "-f",
            "f32le",
            "pipe:1",
        ],
        check=True,
        stdout=subprocess.PIPE,
    ).stdout
    audio = np.frombuffer(raw, dtype=np.float32)
    if channels > 1:
        audio = audio.reshape(-1, channels).T
    else:
        audio = audio.reshape(1, -1)
    return {
        "waveform": torch.from_numpy(np.ascontiguousarray(audio.copy())),
        "sample_rate": sample_rate,
    }


def diarize(source: Path) -> dict[str, Any]:
    from pyannote.audio import Pipeline

    token = load_token()
    started = time.monotonic()
    try:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=token,
        )
    except TypeError:
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
    import torch

    pipeline.to(torch.device("cpu"))
    audio_in = waveform_from_original(source)
    duration = float(audio_in["waveform"].shape[-1] / audio_in["sample_rate"])
    result = pipeline(audio_in)
    if isinstance(result, dict):
        annotation = result.get("speaker_diarization", result)
    else:
        annotation = getattr(result, "speaker_diarization", result)
    raw = [
        {
            "start": round(float(segment.start), 6),
            "end": round(float(segment.end), 6),
            "speaker": str(speaker),
        }
        for segment, _, speaker in annotation.itertracks(yield_label=True)
    ]
    merged = clamp_turns(merge_turns(raw), duration)
    return {
        "audio": str(source.relative_to(ROOT)),
        "duration_sec": duration,
        "model": "pyannote/speaker-diarization-3.1",
        "provider": "pyannote.audio",
        "execution_mode": "local",
        "runtime_sec": round(time.monotonic() - started, 3),
        "raw_turns": raw,
        "merged_turns": merged,
        "holes_ge_0_5_sec": holes(merged, duration),
    }


def prepare() -> dict[str, Any]:
    source = audio_path()
    checkpoint = PYANNOTE_DIR / "meeting_sample.json"
    if checkpoint.exists():
        payload = json.loads(checkpoint.read_text(encoding="utf-8"))
        if payload.get("merged_turns") and payload.get("model") == "pyannote/speaker-diarization-3.1":
            print(json.dumps({"prepare": "reuse_diarization", "rows": len(payload["merged_turns"])}))
        else:
            payload = None
    else:
        payload = None

    if payload is None:
        last_error = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                payload = diarize(source)
                write_json(checkpoint, payload)
                last_error = None
                break
            except Exception as exc:
                last_error = exc
                write_json(
                    PYANNOTE_DIR / f"error_attempt_{attempt}.json",
                    {
                        "attempt": attempt,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    },
                )
                gc.collect()
                if attempt == MAX_RETRIES:
                    raise
        if last_error:
            raise last_error

    duration = float(payload["duration_sec"])
    payload["merged_turns"] = clamp_turns(payload["merged_turns"], duration)
    for index, row in enumerate(payload["merged_turns"]):
        raw_wav = EXTRACTS / f"turn_{index:03d}_raw.wav"
        gained_wav = EXTRACTS / f"turn_{index:03d}_linear.wav"
        extract_stage2(source, row["start"], row["end"], raw_wav, file_duration=duration)
        rms, peak = astats(raw_wav)
        gain = 0.0
        if rms < -30.0 and peak < 0.0 and math.isfinite(rms):
            gain = min(-23.0 - rms, 18.0, -1.0 - peak)
            gain = max(0.0, gain)
        extract_stage2(source, row["start"], row["end"], gained_wav, gain, file_duration=duration)
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
    payload["holes_ge_0_5_sec"] = holes(payload["merged_turns"], float(payload["duration_sec"]))
    write_json(checkpoint, payload)
    write_json(
        PYANNOTE_DIR / "_run.json",
        {
            "model": payload["model"],
            "runtime_sec": payload["runtime_sec"],
            "raw_turns": len(payload["raw_turns"]),
            "merged_rows": len(payload["merged_turns"]),
            "gained_rows": sum(1 for row in payload["merged_turns"] if row.get("gain_db", 0) > 0),
            "holes": len(payload["holes_ge_0_5_sec"]),
        },
    )
    print(
        json.dumps(
            {
                "prepare": "ok",
                "raw_turns": len(payload["raw_turns"]),
                "merged_rows": len(payload["merged_turns"]),
                "runtime_sec": payload["runtime_sec"],
            }
        )
    )
    return payload


def pieces_for_row(
    source: Path, row: dict[str, Any], file_duration: float
) -> list[dict[str, Any]]:
    pieces = []
    piece_start = float(row["start"])
    piece_number = 0
    while piece_start < float(row["end"]) - 1e-9:
        piece_end = min(piece_start + MODEL_LIMIT_SEC, float(row["end"]))
        path = EXTRACTS / f"turn_{row['id']:03d}_piece_{piece_number:02d}_linear.wav"
        extract_stage2(
            source,
            piece_start,
            piece_end,
            path,
            float(row.get("gain_db") or 0.0),
            file_duration=file_duration,
        )
        pieces.append(
            {
                "turn_id": row["id"],
                "piece": piece_number,
                "start": piece_start,
                "end": piece_end,
                "speaker": row["speaker"],
                "path": path,
                "gain_db": row.get("gain_db", 0.0),
            }
        )
        piece_start = piece_end
        piece_number += 1
    return pieces


def format_txt(segments: list[dict[str, Any]]) -> str:
    lines = []
    for item in segments:
        start = item["start"]
        end = item["end"]
        speaker = item["speaker"]
        text = item["text"]
        lines.append(f"[{start:08.3f}–{end:08.3f}] {speaker}: {text}")
    return "\n".join(lines) + "\n"


def gigaam() -> dict[str, Any]:
    import gigaam

    checkpoint = PYANNOTE_DIR / "meeting_sample.json"
    if not checkpoint.exists():
        raise RuntimeError("pyannote checkpoint missing; run prepare first")
    prepared = json.loads(checkpoint.read_text(encoding="utf-8"))
    source = ROOT / prepared["audio"]
    if not source.exists():
        source = audio_path()

    last_error = None
    for attempt in range(1, MAX_RETRIES + 1):
        started = time.monotonic()
        try:
            model = gigaam.load_model("v3_rnnt", fp16_encoder=False, device="cpu")
            recognized: list[dict[str, Any]] = []
            for row in prepared["merged_turns"]:
                for piece in pieces_for_row(source, row, float(prepared["duration_sec"])):
                    raw_text = model.transcribe(str(piece["path"]))
                    text = "" if raw_text is None else str(raw_text)
                    recognized.append(
                        {
                            "id": len(recognized),
                            "turn_id": piece["turn_id"],
                            "piece": piece["piece"],
                            "start": round(float(piece["start"]), 6),
                            "end": round(float(piece["end"]), 6),
                            "speaker": piece["speaker"],
                            "text": text,
                            "gain_db": piece["gain_db"],
                        }
                    )
            runtime_sec = round(time.monotonic() - started, 3)
            payload = {
                "audio": prepared["audio"],
                "language": "ru",
                "duration_sec": prepared["duration_sec"],
                "model": "v3_rnnt",
                "model_label": "gigaam-v3-rnnt",
                "provider": "gigaam",
                "execution_mode": "local",
                "gain": "linear",
                "attempt": attempt,
                "runtime_sec": runtime_sec,
                "diarization": "pyannote/speaker-diarization-3.1",
                "merged_rows": len(prepared["merged_turns"]),
                "holes_ge_0_5_sec": prepared.get("holes_ge_0_5_sec", []),
                "segments": recognized,
            }
            write_json(GIGAAM_DIR / "meeting_sample.json", payload)
            (GIGAAM_DIR / "meeting_sample.txt").write_text(
                format_txt(recognized), encoding="utf-8"
            )
            write_json(
                GIGAAM_DIR / "_run.json",
                {
                    "model": "v3_rnnt",
                    "provider": "gigaam",
                    "execution_mode": "local",
                    "attempt": attempt,
                    "runtime_sec": runtime_sec,
                    "segments": len(recognized),
                    "empty_segments": sum(1 for item in recognized if not item["text"].strip()),
                },
            )
            del model
            gc.collect()
            print(
                json.dumps(
                    {
                        "gigaam": "ok",
                        "attempt": attempt,
                        "segments": len(recognized),
                        "runtime_sec": runtime_sec,
                    }
                )
            )
            return payload
        except Exception as exc:
            last_error = exc
            write_json(
                GIGAAM_DIR / f"error_attempt_{attempt}.json",
                {
                    "attempt": attempt,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                },
            )
            gc.collect()
            if attempt == MAX_RETRIES:
                raise
    raise last_error or RuntimeError("GigaAM failed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["prepare", "gigaam", "all"])
    args = parser.parse_args()
    if args.phase in {"prepare", "all"}:
        prepare()
    if args.phase in {"gigaam", "all"}:
        gigaam()


if __name__ == "__main__":
    main()

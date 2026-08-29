#!/usr/bin/env python3
"""Transcribe isolated 1c clips with faster-whisper large-v3 and optional WhisperX.

Speakers are not inferred here; they are copied from the clip manifest (WhisperX 1b).
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def transcribe_faster_whisper(wav: Path, model) -> dict:
    started = time.monotonic()
    segments, info = model.transcribe(
        str(wav),
        language="ru",
        beam_size=5,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    rows = []
    for seg in segments:
        rows.append(
            {
                "start": round(seg.start, 3),
                "end": round(seg.end, 3),
                "text": (seg.text or "").strip(),
            }
        )
    return {
        "runtime_sec": round(time.monotonic() - started, 3),
        "language": info.language,
        "language_probability": round(float(info.language_probability), 4),
        "segments": rows,
        "text": " ".join(r["text"] for r in rows if r["text"]),
    }


def transcribe_whisperx(wav: Path, asr_model, align_model, align_meta, device: str) -> dict:
    import whisperx

    started = time.monotonic()
    audio = whisperx.load_audio(str(wav))
    result = asr_model.transcribe(audio, batch_size=4, language="ru")
    aligned = whisperx.align(
        result["segments"],
        align_model,
        align_meta,
        audio,
        device,
        return_char_alignments=False,
    )
    rows = []
    for seg in aligned.get("segments") or []:
        rows.append(
            {
                "start": round(float(seg["start"]), 3),
                "end": round(float(seg["end"]), 3),
                "text": (seg.get("text") or "").strip(),
            }
        )
    return {
        "runtime_sec": round(time.monotonic() - started, 3),
        "language": result.get("language"),
        "segments": rows,
        "text": " ".join(r["text"] for r in rows if r["text"]),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--clips-json", type=Path, required=True)
    parser.add_argument("--clips-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--backend", choices=["faster_whisper", "whisperx", "both"], default="faster_whisper")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    manifest = json.loads(args.clips_json.read_text(encoding="utf-8"))
    out = {
        "manifest": str(args.clips_json),
        "clips_dir": str(args.clips_dir),
        "backend": args.backend,
        "device": args.device,
        "compute_type": args.compute_type,
        "clips": [],
    }

    fw_model = None
    wx_asr = None
    wx_align = None
    wx_meta = None
    if args.backend in {"faster_whisper", "both"}:
        from faster_whisper import WhisperModel

        fw_model = WhisperModel(
            "large-v3",
            device=args.device,
            compute_type=args.compute_type,
            cpu_threads=args.threads,
        )
    if args.backend in {"whisperx", "both"}:
        import whisperx

        wx_asr = whisperx.load_model(
            "large-v3",
            args.device,
            compute_type=args.compute_type,
            language="ru",
        )
        wx_align, wx_meta = whisperx.load_align_model(
            language_code="ru", device=args.device
        )

    for clip in manifest["clips"]:
        wav = args.clips_dir / f"{clip['id']}.wav"
        row = {
            "id": clip["id"],
            "speaker_from_whisperx_1b": clip.get("speaker"),
            "speakers_from_whisperx_1b": clip.get("speakers") or [
                {
                    "speaker": clip.get("speaker"),
                    "start": clip["start"],
                    "end": clip["end"],
                }
            ],
            "source_start": clip["start"],
            "source_end": clip["end"],
            "wav": str(wav),
            "why": clip.get("why"),
            "results": {},
        }
        if not wav.exists():
            row["error"] = f"missing wav: {wav}"
            out["clips"].append(row)
            continue
        if fw_model is not None:
            row["results"]["faster_whisper_large_v3"] = transcribe_faster_whisper(
                wav, fw_model
            )
        if wx_asr is not None:
            row["results"]["whisperx_large_v3"] = transcribe_whisperx(
                wav, wx_asr, wx_align, wx_meta, args.device
            )
        print(json.dumps({"id": clip["id"], "keys": list(row["results"])}, ensure_ascii=False))
        out["clips"].append(row)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("wrote", args.output)


if __name__ == "__main__":
    main()

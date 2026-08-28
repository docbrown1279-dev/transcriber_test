#!/usr/bin/env python3
"""Gemini audio transcription fallback (used only when local Whisper cannot run)."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path


PROMPT = """Ты — система распознавания речи для русскоязычных совещаний.
Расшифруй аудио дословно на русском языке.
Верни ТОЛЬКО JSON (без markdown) вида:
{"segments":[{"start":0.0,"end":12.3,"text":"..."}],"text":"полный текст"}
Правила:
- start/end в секундах относительно НАЧАЛА ЭТОГО ФРАГМЕНТА (не всего файла)
- сохраняй смысл, без саммари
- если речь неразборчива, пиши [нрзб]
"""


def split_wav(src: Path, out_dir: Path, chunk_sec: int) -> list[tuple[Path, float]]:
    import subprocess

    out_dir.mkdir(parents=True, exist_ok=True)
    # duration
    probe = subprocess.check_output(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(src),
        ],
        text=True,
    ).strip()
    duration = float(probe)
    chunks = []
    start = 0.0
    idx = 0
    while start < duration:
        out = out_dir / f"chunk_{idx:03d}.wav"
        subprocess.check_call(
            [
                "ffmpeg",
                "-y",
                "-ss",
                str(start),
                "-t",
                str(chunk_sec),
                "-i",
                str(src),
                "-ac",
                "1",
                "-ar",
                "16000",
                str(out),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        chunks.append((out, start))
        start += chunk_sec
        idx += 1
    return chunks


def parse_json_loose(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if not m:
            raise
        return json.loads(m.group(0))


def transcribe_file(model_name: str, audio_path: Path) -> dict:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_name)
    uploaded = genai.upload_file(str(audio_path))
    # wait until processed
    for _ in range(60):
        meta = genai.get_file(uploaded.name)
        if meta.state.name == "ACTIVE":
            break
        if meta.state.name == "FAILED":
            raise RuntimeError(f"upload failed: {audio_path}")
        time.sleep(2)
    resp = model.generate_content([PROMPT, uploaded])
    raw = resp.text or ""
    try:
        data = parse_json_loose(raw)
    except Exception:
        data = {"segments": [{"start": 0.0, "end": 0.0, "text": raw}], "text": raw}
    return {"raw_response": raw[:5000], "parsed": data}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="models/gemini-3.5-transcribe")
    parser.add_argument("--chunk-sec", type=int, default=480)
    parser.add_argument("--offset-sec", type=float, default=0.0, help="Add to all timestamps")
    args = parser.parse_args()

    audio = Path(args.audio)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    work = out.parent / f"{out.stem}_chunks"
    t0 = time.time()

    chunks = split_wav(audio, work, args.chunk_sec)
    all_segments = []
    texts = []
    api_calls = []
    for path, offset in chunks:
        t1 = time.time()
        # Prefer transcribe model; fall back to flash if needed
        model_used = args.model
        try:
            result = transcribe_file(model_used, path)
        except Exception as e:
            model_used = "models/gemini-2.5-flash"
            result = transcribe_file(model_used, path)
            api_calls.append({"chunk": path.name, "fallback_reason": str(e)[:200]})
        elapsed = time.time() - t1
        api_calls.append({"chunk": path.name, "model": model_used, "sec": round(elapsed, 2)})
        parsed = result["parsed"]
        segs = parsed.get("segments") or []
        chunk_text = parsed.get("text") or " ".join(s.get("text", "") for s in segs)
        texts.append(chunk_text.strip())
        for s in segs:
            all_segments.append(
                {
                    "start": round(float(s.get("start", 0.0)) + offset + args.offset_sec, 3),
                    "end": round(float(s.get("end", 0.0)) + offset + args.offset_sec, 3),
                    "text": (s.get("text") or "").strip(),
                }
            )
        # cache per chunk
        (work / f"{path.stem}.json").write_text(
            json.dumps({"offset": offset, "model": model_used, "result": result}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    payload = {
        "lib": "gemini-api-fallback",
        "model": args.model,
        "audio": str(audio),
        "runtime_sec": round(time.time() - t0, 2),
        "api_calls": api_calls,
        "text": "\n".join(t for t in texts if t),
        "segments": all_segments,
        "notes": "Local Whisper unavailable due to egress block on model hosts; Gemini used per Stage1 policy.",
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".txt").write_text(payload["text"] + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "segments": len(all_segments), "runtime_sec": payload["runtime_sec"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Meeting summary via local LLM if available, else Gemini API fallback."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

PROMPT = """Ты помощник по протоколам совещаний. По транскрипту на русском сделай:
1) Краткое саммари (5-8 предложений)
2) Список решений
3) Список действий (кто/что, если известно)
4) Открытые вопросы

Ответь на русском. Не выдумывай факты, которых нет в тексте. Если данных мало — так и напиши.
"""


def summarize_gemini(model_name: str, text: str) -> str:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    model = genai.GenerativeModel(model_name)
    # truncate if huge
    clipped = text
    if len(clipped) > 120000:
        clipped = clipped[:120000]
    resp = model.generate_content([PROMPT, clipped])
    return resp.text or ""


def try_local_ollama(model: str, text: str) -> tuple[bool, str]:
    import urllib.request

    payload = json.dumps(
        {
            "model": model,
            "prompt": PROMPT + "\n\n" + text[:50000],
            "stream": False,
        }
    ).encode()
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            data = json.loads(r.read().decode())
            return True, data.get("response", "")
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--chunks", default="")
    parser.add_argument("--out", required=True)
    parser.add_argument("--gemini-model", default="models/gemini-2.5-flash")
    args = parser.parse_args()

    path = Path(args.transcript)
    data = json.loads(path.read_text(encoding="utf-8")) if path.suffix == ".json" else {"text": path.read_text(encoding="utf-8")}
    text = data.get("text") or ""

    # Prefer chunk concatenation for structure
    if args.chunks:
        cpath = Path(args.chunks)
        if cpath.exists():
            cdata = json.loads(cpath.read_text(encoding="utf-8"))
            parts = []
            for ch in cdata.get("chunks") or []:
                parts.append(f"[Чанк {ch.get('id')}]\n{ch.get('text','')}")
            if parts:
                text = "\n\n".join(parts)

    t0 = time.time()
    local_ok, local_out = try_local_ollama("qwen2.5:7b-instruct", text)
    if local_ok and local_out.strip():
        runtime = "ollama"
        model = "qwen2.5:7b-instruct"
        summary = local_out
        notes = "Local Ollama summary succeeded."
    else:
        runtime = "gemini-api-fallback"
        model = args.gemini_model
        summary = summarize_gemini(model, text)
        notes = f"Local LLM unavailable ({local_out[:200]}); Gemini used sparingly for summary."

    # Heuristic hallucination flag: empty fluff / refuses
    hall = False
    low = summary.lower()
    if len(summary.strip()) < 80:
        hall = True
    if "недостаточно данных" in low and len(text) > 2000:
        # may be overly cautious, not necessarily hallucination
        hall = False

    payload = {
        "runtime": runtime,
        "model": model,
        "status": "success" if summary.strip() else "fail",
        "runtime_sec": round(time.time() - t0, 2),
        "hallucination_flag": hall,
        "summary": summary,
        "notes": notes,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    out.with_suffix(".md").write_text(summary + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out), "runtime": runtime, "runtime_sec": payload["runtime_sec"], "chars": len(summary)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

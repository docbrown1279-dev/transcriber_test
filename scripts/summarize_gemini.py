#!/usr/bin/env python3
"""Make one text-only Gemini fallback call without logging credentials."""

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--model", default="gemini-2.5-flash")
    args = parser.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise SystemExit("Gemini API credential is not available")

    prompt = (
        "Ты аккуратный секретарь русскоязычных совещаний. Составь: "
        "1) краткое саммари; 2) только явно принятые решения; "
        "3) действия и ответственных, только если ответственный явно назван. "
        "Не придумывай ответственных. Неуверенные места пометь.\n\n"
        f"СТЕНОГРАММА:\n{args.transcript.read_text(encoding='utf-8')}"
    )
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 1024},
    }
    request = urllib.request.Request(
        (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{args.model}:generateContent?key={api_key}"
        ),
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        raise SystemExit(f"Gemini request failed with HTTP {error.code}") from None
    runtime_sec = round(time.monotonic() - started, 3)
    summary = "".join(
        part.get("text", "")
        for candidate in result.get("candidates", [])
        for part in candidate.get("content", {}).get("parts", [])
    ).strip()
    if not summary:
        raise SystemExit("Gemini returned no text")

    markdown_path = Path(f"{args.output}.md")
    metadata_path = Path(f"{args.output}.json")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(summary + "\n", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "execution_mode": "api",
                "provider": "Google Gemini",
                "model": args.model,
                "input_artifact": str(args.transcript),
                "runtime_sec": runtime_sec,
                "usage": result.get("usageMetadata"),
                "artifact": str(markdown_path),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"runtime_sec": runtime_sec, "characters": len(summary)}))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate one local Russian meeting summary with a GGUF model."""

import argparse
import json
import time
from pathlib import Path

from llama_cpp import Llama


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("transcript", type=Path)
    parser.add_argument("model", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()

    transcript = args.transcript.read_text(encoding="utf-8")
    started = time.monotonic()
    llm = Llama(
        model_path=str(args.model),
        n_ctx=8192,
        n_threads=args.threads,
        n_threads_batch=args.threads,
        n_batch=512,
        verbose=False,
    )
    response = llm.create_chat_completion(
        messages=[
            {
                "role": "system",
                "content": (
                    "Ты аккуратный секретарь русскоязычных совещаний. "
                    "Не добавляй факты, которых нет в стенограмме."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Составь по стенограмме: 1) краткое саммари; "
                    "2) принятые решения; 3) действия и ответственных, только "
                    "если они явно названы. Неуверенные места пометь.\n\n"
                    f"СТЕНОГРАММА:\n{transcript}"
                ),
            },
        ],
        max_tokens=768,
        temperature=0.2,
        top_p=0.9,
    )
    runtime_sec = round(time.monotonic() - started, 3)
    summary = response["choices"][0]["message"]["content"].strip()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    markdown_path = Path(f"{args.output}.md")
    metadata_path = Path(f"{args.output}.json")
    markdown_path.write_text(summary + "\n", encoding="utf-8")
    metadata_path.write_text(
        json.dumps(
            {
                "execution_mode": "local",
                "provider": "llama.cpp",
                "model": args.model.name,
                "input_artifact": str(args.transcript),
                "runtime_sec": runtime_sec,
                "usage": response.get("usage"),
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

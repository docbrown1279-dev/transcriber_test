#!/usr/bin/env python3
"""Semantic chunking via neighbor cosine similarity (Gemini embeddings fallback)."""

from __future__ import annotations

import argparse
import json
import os
import re
import time
from pathlib import Path


def sentence_split(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?…])\s+", text.strip())
    out = []
    buf = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if len(buf) + len(p) < 40:
            buf = (buf + " " + p).strip()
            continue
        if buf:
            out.append(buf)
        buf = p
    if buf:
        out.append(buf)
    return out


def embed_texts(model_name: str, texts: list[str]) -> list[list[float]]:
    import google.generativeai as genai

    genai.configure(api_key=os.environ["GEMINI_API_KEY"])
    vectors = []
    for i, t in enumerate(texts):
        # batch small to stay safe
        res = genai.embed_content(model=model_name, content=t, task_type="clustering")
        emb = res["embedding"]
        vectors.append(emb)
        if (i + 1) % 20 == 0:
            time.sleep(0.2)
    return vectors


def cosine(a: list[float], b: list[float]) -> float:
    import math

    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--threshold", type=float, default=0.7)
    parser.add_argument("--model", default="models/text-embedding-004")
    args = parser.parse_args()

    path = Path(args.transcript)
    raw = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        data = json.loads(raw)
        text = data.get("text") or ""
        segments = data.get("segments") or []
    else:
        text = raw
        segments = []

    sentences = sentence_split(text)
    # Cap for API economy: if too many, merge into windows of ~2 sentences
    if len(sentences) > 120:
        merged = []
        for i in range(0, len(sentences), 2):
            merged.append(" ".join(sentences[i : i + 2]))
        sentences = merged

    t0 = time.time()
    vectors = embed_texts(args.model, sentences)
    sims = []
    breaks = []
    for i in range(len(vectors) - 1):
        s = cosine(vectors[i], vectors[i + 1])
        sims.append(round(s, 4))
        if s < args.threshold:
            breaks.append(i + 1)

    # Build chunks
    chunks = []
    start = 0
    for b in breaks + [len(sentences)]:
        chunk_sents = sentences[start:b]
        if chunk_sents:
            chunks.append({"id": len(chunks), "text": " ".join(chunk_sents), "n_sentences": len(chunk_sents)})
        start = b

    # Spot-check: inspect a few break contexts
    spot = []
    for b in breaks[:5]:
        left = sentences[b - 1] if b - 1 >= 0 else ""
        right = sentences[b] if b < len(sentences) else ""
        sim = sims[b - 1] if b - 1 < len(sims) else None
        # Heuristic: topic change if different key nouns / low sim already
        verdict = "ok" if sim is not None and sim < args.threshold else "n/a"
        spot.append({"break_after": b - 1, "sim": sim, "left": left[:220], "right": right[:220], "verdict": verdict})

    payload = {
        "method": "semantic_neighbor_cosine",
        "embedding_model": args.model,
        "threshold": args.threshold,
        "num_sentences": len(sentences),
        "num_chunks": len(chunks),
        "num_breaks": len(breaks),
        "mean_sim": round(sum(sims) / len(sims), 4) if sims else None,
        "min_sim": min(sims) if sims else None,
        "runtime_sec": round(time.time() - t0, 2),
        "spot_check_samples": spot,
        "chunks": chunks,
        "similarities": sims,
        "notes": "Local sentence-transformers blocked (HF egress); Gemini embeddings used as fallback.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        json.dumps(
            {
                "out": str(out),
                "num_chunks": payload["num_chunks"],
                "num_breaks": payload["num_breaks"],
                "mean_sim": payload["mean_sim"],
                "runtime_sec": payload["runtime_sec"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()

# AGENTS.md — diarization algorithm research (cloud)

## Mission

Bounded **research** on clustering algorithms over **existing** WeSpeaker
embeddings: spectral, hybrid (AHC → change-point spectral), optional
anchor→assign. Measure cold/warm load vs embed wall on a 5-minute clip.

**Not** a product stage. No `coder_*.md` / `tester_*.md`. No production
`src/`/`config/` edits unless a throwaway runner under `cloud_out/scratch/`.

## Hard rules

1. Never read `eval/`, `.env`, secrets, `docs/research_results/`, `data/`.
2. Only `cloud_in/inputs/` audio.
3. No gold invention. No duration-based speaker deletion as the main method.
4. No hard prior that speaker count must be 2–4 (may be 10+).
5. No ASR/LLM/Jina/second embedder/H0 product warmup.
6. Commit + push branch; do **not** open a PR.

## Deliverables

`cloud_out/report.md`, `results.json`, `run_meta.json`, timelines, optional scratch runner.

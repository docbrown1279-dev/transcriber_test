# AGENTS.md — two-pass diarization research (cloud)

## Mission

Research **draft (VAD units) → fine (WeSpeaker)** clustering variants.
Throwaway code under `cloud_out/scratch/` only. No production PR.

## Hard rules

1. Never read `eval/`, `.env`, secrets, `docs/research_results/`, `data/`.
2. Only `cloud_in/inputs/` audio.
3. No gold invention. No crumb≤3s as primary method. No K∈[2,4] mandate.
4. **Clarify:** “spectral analysis” in stage 1B/1C = **cheap signal features**, not WeSpeaker.
5. No ASR/LLM/Jina/second embedder.
6. Commit + push branch; do **not** open a PR.

## Deliverables

`cloud_out/report.md`, `results.json`, `run_meta.json`, timelines, scratch runners.

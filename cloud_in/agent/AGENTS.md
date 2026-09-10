# AGENTS.md — diarization / TTFT research (cloud role)

## Mission

Run a **bounded research experiment** on WeSpeaker **window size** and
**clustering** (threshold + crumb merge). Produce tables and a recommendation in
`cloud_out/`. Soft quality band: **~2–4** substantial speakers per clip.

This is **not** a product stage: there are **no** `coder_*.md` / `tester_*.md`
instructions here on purpose (token cost). Do **not** implement production
pipeline features, contracts, UI, or merge-ready refactors.

## What to read, in order

1. `cloud_in/HANDOFF.md`
2. `cloud_in/prompt.md`
3. `cloud_in/agent/rules.md` (tooling only; ignore product-gate ceremony)
4. `cloud_in/inputs/` (audio + CLIP_INDEX)

## Hard rules

1. **Never read** `eval/`, `.env`, secrets, `docs/research_results/`, or `data/`.
2. Process **only** audio under `cloud_in/inputs/`.
3. **No gold labels** in the pack — do not invent them. Report stats + timelines.
4. **No production code** in `src/` / `config/` for this run unless a tiny
   throwaway helper under `scripts/` or `cloud_out/scratch/` is required to run
   the grid. Prefer calling existing diarization APIs / a one-off script.
5. **No ASR**, no LLM, no Jina, no pyannote, no H0 warmup work.
6. Do not open a PR. Commit + push the handoff branch with `cloud_out/` reports.
7. Never print secrets. Prefer `.trash/` over `rm -rf`.

## Budgets

| Block | Cap |
|---|---|
| Window presets (S1) | baseline + ≤2 coarser presets |
| Cluster thresholds | ≤4 values around 0.85 |
| Full 15′ audio | **not packed** — do not fetch |
| ASR / Gemini | 0 |
| Package installs | only if WeSpeaker deps missing; `uv` only |

## Deliverables

1. `cloud_out/report.md` — English tables + recommendation
2. `cloud_out/results.json` — machine-readable grid
3. `cloud_out/run_meta.json` — host, wall, peak RSS, versions
4. Optional: `cloud_out/timelines/*.json` — per-clip speaker turns for local review
5. Push branch named in `HANDOFF.md` (no PR)

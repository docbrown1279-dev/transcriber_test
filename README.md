# Speech recognition research

Local stack research for **Russian meeting / interview transcription**.

Repo: `transcriber_test` (`docbrown1279-dev`).

## Status

**Stage 1b — coherent text + diarization** (current).  
Stage 1a (medium / ffmpeg / chunking / summary) is recorded on `cursor/stage1-asr-research-dc41`.  
**Stage 2 — systematic testing** — deferred.

Plan: [`docs/research_plan.md`](docs/research_plan.md)  
Agent entrypoint: [`AGENTS.md`](AGENTS.md)

## Fixture

Example meeting audio:

- `docs/Голос 002.m4a`
- `data/fixtures/meeting_sample.m4a` (symlink)

## Launch cloud / Cursor agent (Stage 1b)

1. Set the Cloud Agent **base branch** to `cursor/stage1-asr-research-dc41` (do not start from empty `main` results).
2. Paste [`docs/prompts/stage1b_cloud_agent.md`](docs/prompts/stage1b_cloud_agent.md).
3. Secrets: **`HF_TOKEN` is required** (pyannote / WhisperX).
4. Review the same branch: `results/reports/` plus new `results/asr/` artifacts.

## Local humans

Do not install packages until you approve the list in `docs/environment.md`. Stage 2 test harness is intentionally not set up yet.

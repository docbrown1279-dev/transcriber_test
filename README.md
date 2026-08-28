# Speech recognition research

Local stack research for **Russian meeting / interview transcription**.

Repo: `transcriber_test` (`docbrown1279-dev`).

## Status

**Stage 1 — technology research and reports** (current).  
**Stage 2 — systematic testing** — deferred; details later.

Plan: [`docs/research_plan.md`](docs/research_plan.md)  
Agent entrypoint: [`AGENTS.md`](AGENTS.md)

## Fixture

Example meeting audio:

- `docs/Голос 002.m4a`
- `data/fixtures/meeting_sample.m4a` (symlink)

## Launch cloud / Cursor agent (Stage 1)

1. Open this repo in Cursor (Agents Window / Cloud Agent).
2. Ensure the agent can read `AGENTS.md` and `.cursor/skills/asr-research/`.
3. Paste the prompt from [`docs/prompts/stage1_cloud_agent.md`](docs/prompts/stage1_cloud_agent.md).
4. Approve any dependency installs the agent proposes (`docs/environment.md`).
5. When finished, review `results/reports/research_report.json` and `notes.md`.

## Local humans

Do not install packages until you approve the list in `docs/environment.md`. Stage 2 test harness is intentionally not set up yet.

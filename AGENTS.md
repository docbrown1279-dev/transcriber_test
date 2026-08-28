# AGENTS.md — Speech Recognition Research

## Mission

Find a workable local stack `ASR + denoise + chunking + local LLM` for Russian meeting/interview transcription on CPU. Product goal later: transcribe meetings and interviews. **This repo is currently Stage 1 only: technology research and reports.** Stage 2 (systematic testing harness) will be specified later — do not invent a full test suite yet.

## Role

You are the **Researcher** agent. Read and follow:

1. [`docs/research_plan.md`](docs/research_plan.md) — authoritative research plan and quality criteria
2. [`.cursor/skills/asr-research/SKILL.md`](.cursor/skills/asr-research/SKILL.md) — step-by-step Stage 1 workflow
3. [`docs/schemas/research_report.schema.json`](docs/schemas/research_report.schema.json) — report schema

## Current stage (Stage 1)

| In scope | Out of scope |
|---|---|
| Install/run Whisper-family ASR | NeMo / exotic ASR (unless Whisper fails completely) |
| Denoise as a **separate** track | Mixing denoise into ASR experiments without A/B |
| Semantic chunking + local embeddings | Production pipeline / UI |
| Local LLM summary (Qwen-class); API LLM only as fallback | Using Gemini/NVIDIA as the default path |
| `research_report.json` + `notes.md` | Stage 2 test matrix (deferred) |

## Fixtures

| Path | Description |
|---|---|
| `data/fixtures/meeting_sample.m4a` | Example meeting (symlink → `docs/Голос 002.m4a`) |
| `docs/Голос 002.m4a` | Same file, original location |

If no other fixtures exist, use this sample. Prefer creating additional synthetic/noisy variants under `data/processed/` rather than replacing the original.

## Credentials & APIs

Secrets live in environment variables / Cursor secrets (never commit, never print values). Expected names: see [`docs/environment.md`](docs/environment.md#credentials--apis).

| Secret | Use |
|---|---|
| Hugging Face token (`HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN`) | Download gated / rate-limited models from Hub |
| Gemini API key | Cloud LLM / multimodal via API |
| NVIDIA API key | NVIDIA NIM / catalog models via API |

**Policy:** local models are the default. Call Gemini or NVIDIA **sparingly** — only when a local model cannot do the job or would take unreasonably long (e.g. huge LLM summary on weak CPU). Daily quotas apply; batch and cache results; log each API call in `notes.md` (provider + purpose, **not** the key).

Scripts may read keys from the environment and call APIs; do not hardcode secrets.

## Hard constraints

- Prefer **CPU**-friendly **local** stacks; note GPU if available but do not require it.
- Max **3 attempts** per ASR library/config family.
- Quality gate: Russian word ratio ≥ **0.9**, then human-like sample check on 3–5 fragments.
- **Unattended Stage 1:** you **may** create `.venv` and install packages/models from `docs/environment.md` (and minimal extras required by a block) **without waiting** for further human approval. Prefer the documented starter set; note exact versions in `notes.md`.
- Do **not** delete audio or results; move unwanted files to `.trash/` if needed.
- **Do** commit and push research outputs to the agent working branch / PR when finished (or at stable checkpoints). Avoid force-push to `main`.
- Do **not** read aloud, log, or commit secret values.
- Write all agent-facing notes and reports in **Russian** (domain language); code/comments in English is fine.

## Deliverables (required)

Write under `results/reports/`:

1. `research_report.json` — matches schema
2. `notes.md` — problems, observations, failed attempts
3. Intermediate artifacts under `results/{asr,denoise,chunking,llm}/` with clear names

## Environment bootstrap

See [`docs/environment.md`](docs/environment.md). Inventory the machine, then install and continue — **do not stop for install approval** on unattended Stage 1 runs.

## Launch checklist

```
- [ ] Read docs/research_plan.md
- [ ] Read .cursor/skills/asr-research/SKILL.md
- [ ] Inventory hardware + existing tools
- [ ] Install deps (.venv + packages/models as needed) — no wait
- [ ] Run ASR block → denoise → chunking → LLM (or stop early with justified FAIL)
- [ ] Write research_report.json + notes.md
- [ ] Commit/push branch or PR with results
- [ ] Summarize recommended MVP stack in recommendations
```

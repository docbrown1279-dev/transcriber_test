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
- Quality gate: Russian word ratio ≥ **0.9**, then human-like sample check on 3–5 fragments.
- **Unattended Stage 1:** you **may** create `.venv` and install packages/models from `docs/environment.md` (and minimal extras required by a block) **without waiting** for further human approval. Prefer the documented starter set; note exact versions in `notes.md`.
- Do **not** delete audio or results; move unwanted files to `.trash/` if needed.
- **Do** commit and push research outputs to the agent working branch / PR when finished (or at stable checkpoints). Avoid force-push to `main`.
- Do **not** read aloud, log, or commit secret values.
- Write all agent-facing notes and reports in **Russian** (domain language); code/comments in English is fine.

## Hard budgets (token / API / attempt caps)

Do **not** infinite-retry. An attempt cap includes the initial run (so three
attempts means initial + at most two retries). On hitting a cap: mark
`fail`/`skipped`, write what you have, commit/push, stop that block. During an
unattended run, do not ask for confirmations: make a bounded reasonable choice,
record it, and continue.

| Block | Cap |
|---|---|
| ASR | **≤ 3** local attempts total. Start `faster-whisper medium`; use `large-v3` only after a completed quality failure. If HF transport fails, use one official `openai-whisper medium` attempt via Azure instead of retrying the same host. Optional **1** `whisper.cpp` timing run only with weights already available. |
| Denoise | **≤ 3** methods (e.g. ffmpeg filter, DeepFilterNet, RNNoise). **1** A/B (before/after) per method. No re-tunes. |
| Chunking | **≤ 2** embedding model tries. **1** threshold (default ~0.7); one optional nudge only if clearly broken. |
| Local LLM summary | **≤ 1** model / runtime try. Soft wall: ~10 min gen; if exceeded → stop local, optionally one API call. |
| Gemini API | **≤ 3** calls for the whole Stage 1 run |
| NVIDIA API | **≤ 3** calls for the whole Stage 1 run |
| Network preflight | **1** anonymous probe + optional **1** token comparison |
| Package installation | **≤ 2** attempts per tool family, then skip that path |
| Agent loops | No “try again from scratch” of the whole pipeline. No package install churn — install once per tool family. |

Prefer finishing a **thin** complete report over exhausting budgets on one block.

## Evidence and provenance gates

These rules prevent a cloud result from being reported as a local-stack result:

1. **Network preflight before ASR:** anonymously fetch the public
   `Systran/faster-whisper-medium` config and record DNS/TLS/redirect results in
   `results/asr/network_preflight.json`. Follow redirects and name the exact
   blocked host (including Xet/LFS hosts). A missing `HF_TOKEN` is not an auth
   failure for this public model.
   If HF fails before HTTP, use the official `openai-whisper medium` Azure
   checkpoint as the one permitted local transport fallback; do not try another
   HF model at the same blocked endpoint.
2. **No API ASR substitution:** Gemini, NVIDIA, or any other remote ASR must not
   replace or count as a Whisper attempt or ASR success. Do not send audio to an
   API during Stage 1.
3. **API scope:** Gemini/NVIDIA may only summarize or secondarily review text
   produced by a successful local Whisper run, and only after the local LLM
   attempt fails or exceeds its time wall.
4. **Local dependency gate:** denoise A/B, chunking, and summary require a
   transcript produced locally in this run (or an explicitly identified prior
   local artifact). If both permitted local Whisper transports are blocked,
   mark ASR `fail` with `failure_kind: network`; mark dependent blocks
   `skipped`; finish the report.
5. **Provenance:** every result names `execution_mode` (`local` or `api`),
   provider/model, and input artifact. Never label API output as local.
6. **Resume, do not repeat:** on a restarted agent, inspect existing artifacts
   and attempt counters first. Do not repeat completed API calls or experiments.

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

# AGENTS.md — meeting transcriber, product development (cloud role)

## Mission

Build the `demo` profile of a Russian meeting-minutes application: audio → normalize → VAD →
diarization → ASR → term suggestions → semantic chunking → chapter titles → insights → report →
simple web UI. Development runs stage by stage; each cloud run delivers **one** stage with a
passing gate and a PR.

**This is product development, not research.** The technology stack is already frozen by the
research phase — do not re-evaluate it, do not benchmark alternatives, do not "improve" it with a
different model.

## What to read, in order

1. `cloud_in/HANDOFF.md` — current stage, branch, deliverables
2. `cloud_in/prompt.md` — the stage task, inputs, gate, stop-list
3. `cloud_in/agent/rules.md` — coding, testing and reporting norms
4. `cloud_in/inputs/` — everything the stage needs (stack summary, artifacts, audio, extras)
5. Product specs already in git when listed in the prompt: `agent_docs/instructions/`,
   `agent_docs/contracts/` (not research archives)

**Do not read** `docs/research_results/` — the local planner already distilled decisions into
`cloud_in/inputs/STACK.md` and this file. Opening research reports to re-argue the stack is a
stop violation.

Never wait for human approval mid-run: the run is unattended. Make a bounded, documented choice
and continue; if a decision is genuinely blocked, write `cloud_out/BLOCKED.md` and stop.

## Preflight (always the first step)

Check and report before installing anything:

| Item | On failure |
|---|---|
| `cloud_in/agent/{AGENTS.md,rules.md}`, `cloud_in/prompt.md`, `cloud_in/HANDOFF.md` | stop, `cloud_out/BLOCKED.md` |
| Every file listed under "Inputs" in `cloud_in/prompt.md` | stop, name the missing files exactly |
| Secrets required by the stage (`GEMINI_API_KEY`, `HF_TOKEN`) | D2 titles need `GEMINI_API_KEY` — missing key → BLOCKED/FAIL for titles; missing `HF_TOKEN` only if weights not cached. Otherwise skip only the dependent steps, finish the rest, record it |
| Host inventory (`nproc`, `free -h`, `df -h .`, `ffmpeg -version`, `python3 --version`) | record in `cloud_out/run_meta.json` |

## Frozen stack (do not reopen)

| Layer | Decision | Source |
|---|---|---|
| Loudness | Dual-path: `normalized.wav` (+ linear gain if RMS < −30 dBFS); VAD `vad_input.wav` = raw 16 kHz (no dynaudnorm) | `reports/1e`, D1 Silero T2 |
| Denoise | **none** — measured harmful or useless | `reports/1a`, `1b` |
| VAD | Silero on raw `vad_input` (snakers4+context); thr 0.45; `min_silence_ms=350`; TEN hole-fill disabled by default | `reports/1f2`, D1 Silero T2 |
| Diarization | WeSpeaker on `normalized.wav`; premerge ≤0.5 s; same-speaker gap ≤0.3 s; absorb <1.0 s | `reports/1f`, D1 T2 |
| ASR | GigaAM `v3_rnnt` (CPU torch runtime); ≤25 s splits; per-turn linear gain | `reports/1e`, D1 dual-path |
| Terms | suggestions only, never a silent rewrite of the transcript | `reports/2b` |
| Chunking | variant C: speaker packing (gap ≤2 s) + `rubert-tiny2`, threshold 0.70 | `reports/2b/conclusions.md` |
| Titles | prompt P1, ≤10 words, no "обсуждение …" stamps | `reports/3` |
| Insights / report | per-chapter extract, then one summary/report call after merge | `reports/3b`, `3c` |
| LLM in the cloud | Gemini 2.5 Flash, text only | `reports/3c` |
| Timecodes | copied from ASR segment boundaries; the model never emits time | research plan |

Whisper, pyannote, denoise filters, late chunking (Jina), local LLM and NeMo are **out of scope
for cloud runs**. They exist as registry stubs only.

## Hard rules

1. **Never read** `eval/`, `.env`, `.credentials`, any secret file, or `docs/research_results/`.
   Gold and research archives stay with the local planner; gates never need them.
2. **Never send audio to an API.** LLM calls are text-only.
3. **Never read** anything under `data/` or paths outside the pack. Process **only** files under
   `cloud_in/inputs/`. If the stage pack includes the full meeting audio (e.g. D1
   `voice_002.m4a`), running ASR on that packed file is required and allowed. Do not invent
   extra audio sources.
4. **Never print or commit secret values.** Log a call as "provider + purpose".
5. **Never weaken a gate.** A failing threshold is a `FAIL` report, not a new threshold.
6. **Never fabricate data.** No fixture, placeholder or model-invented value in a production
   artifact path; an unimplemented stage raises a clear error instead.
7. **Do not delete** files. Move unwanted ones to `.trash/`.
8. Write outputs to `cloud_out/`, code to `src/`, tests to `tests/`; do not touch `docs/`,
   `agent_docs/contracts/`, `.cursor/`, `data/`, `eval/`.

## Budgets (a cap includes the first attempt)

| Block | Cap |
|---|---|
| Package installs | ≤2 attempts per tool family, then record a blocker and skip that path |
| ASR runs | ≤3 per stage total (D1: 1× full packed meeting required + optional short-clip runs within the remaining budget) |
| Gemini calls | ≤20 per run, cached into artifacts |
| Local LLM | not run in the cloud at all |
| 15-minute hardware slice | stage D5 only, ≤2 runs |
| Gate retries | ≤2 honest fix attempts, then `FAIL` report + PR |

Prefer a thin, honest, complete stage over an exhausted budget on one detail.

## Deliverables of every run

1. Code under `src/` and tests under `tests/` for the stage in `prompt.md`
2. `cloud_out/gate_D{N}.md` — every check id with value, threshold, status, plus the agent
   judgement section the gate asks for
3. `cloud_out/run_meta.json` — branch, commit, host inventory, package versions, wall time,
   peak RSS, LLM call count
4. Appended status lines in `agent_docs/progress/stage_D{N}.md` (append-only)
5. Commit + push the branch named in `HANDOFF.md`. **Do not open a PR** — the local operator
   creates a draft PR with `scripts/cloud_pr.sh` after ingest. Never force-push `main`.

## Language

Code, comments, commit messages, gate reports and `run_meta.json` in **English**. Docstrings on
public APIs and any human-facing notes in **Russian**.

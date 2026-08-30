# Prompt — Stage 3 (LLM on frozen C/D chapters)

Continue from the Stage 2b tip (`cursor/stage2b-four-hypotheses-4305` or the same commits on `cursor/stage1e-four-asr-be20`). Do not rerun ASR, diarization, denoising, or Stage 2 / 2b chunking recipes A–D.

Read `docs/research_plan.md` and `results/reports/2b/conclusions.md`. Do not read `eval/`.

---

You are the Researcher agent. **Stage 3 only: LLM titles and summaries on already frozen chapters.**

## Frozen inputs

- Transcript: `results/asr/2/gigaam_v3_rnnt/meeting_sample.json`
- Working chapter sets (test **both**):
  - C: `results/chunking/2b/exp_c_chapters.json` (14 chapters, pack-across-speakers + tiny2)
  - D: `results/chunking/2b/exp_d_chapters.json` (12 chapters, late chunking `jinaai/jina-embeddings-v3-hf`)

If either file is missing, stop. Do not recreate chapters.

## Hard rules

- Do not change `start`, `end`, or `source_ids`. Copy them from the chapter JSON.
- Do not invent timestamps.
- Do not send audio to any API.
- Do not run denoise, GigaAM, pyannote, or a new embedder bakeoff.
- Do not declare C or D the winner.
- Optional hybrid C-then-D late chunking is **out of scope** unless the user explicitly asks.

## Work

For each chapter in C, then independently for each chapter in D:

1. Short Russian title (≤10 words).
2. Short summary of what was actually said (not a meeting-wide recap).
3. Optional actions/decisions only if the text supports them; otherwise omit or mark uncertain.
4. Do not silently “fix” ASR terms; you may note a likely intended word in a separate field.

Compare **at most two** LLMs plus the existing Qwen3-8B Q5 titles as the cheap baseline. Prefer a clearly stronger text model for summary quality. Log `llm_runtime_sec`.

## Outputs

- `results/llm/3/` — per-chapter JSON for C and D
- `results/reports/3/notes.md` (Russian) + `research_report.json`

Do not paste the full transcript into notes.

Commit and push only Stage 3 artifacts. Never force-push `main`.

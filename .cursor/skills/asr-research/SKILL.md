---
name: asr-research
description: Runs Stage 1 speech recognition research (Whisper ASR, denoise, semantic chunking, local LLM summary) and writes research_report.json. Use when starting ASR research, meeting transcription experiments, Whisper/faster-whisper evaluation, denoise A/B, or producing Stage 1 reports.
---

# ASR Research — Stage 1

## When to use

Cloud or local agent tasked with Stage 1 technology evaluation for Russian meeting transcription.

## Before any install

1. Read `docs/research_plan.md` and `AGENTS.md`.
2. Inventory host:

```bash
uname -a
nproc
free -h
df -h .
python3 --version
ffmpeg -version | head -1
command -v nvidia-smi && nvidia-smi || echo "no GPU"
```

3. Propose packages from `docs/environment.md`. **Stop and wait for human approval before installing.**
4. Confirm credentials are available as env vars (do not print values): HF token for Hub downloads; Gemini + NVIDIA for API fallbacks. See `docs/environment.md` § Credentials.

## Local first, API sparingly

- **Default:** local Whisper / embeddings / Qwen (or similar).
- **Hugging Face:** use `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` when downloading models (`huggingface-cli` / `huggingface_hub`).
- **Gemini + NVIDIA APIs:** allowed inside scripts, but **economical use only** — daily limits. Use when:
  - local model fails quality/runtime gates, or
  - local run would be unreasonably long (document estimate), or
  - a one-shot judgment/summary needs a stronger model after a local attempt.
- Prefer short prompts, small context, one call per decision; cache outputs under `results/`.
- Record every API call in `notes.md`: provider, model, why local was insufficient, approx tokens/time. Never log API keys.

## Workflow order

Copy and track:

```
Stage 1 Progress:
- [ ] 0. Inventory + approved deps
- [ ] 1. ASR (faster-whisper medium / large-v3)
- [ ] 2. Denoise A/B on worst-quality audio
- [ ] 3. Semantic chunking (embeddings)
- [ ] 4. Local LLM summary
- [ ] 5. research_report.json + notes.md
```

Do blocks in order. If ASR fails all attempts, still write the report with FAIL and skip dependent blocks that need usable transcript (note why).

### 1. ASR

- Primary: `faster-whisper` models `medium`, then `large-v3` if needed.
- Optional: `whisper.cpp` for CPU speed comparison.
- Input: `data/fixtures/meeting_sample.m4a` (and variants under `data/processed/` if created).
- Output per run: transcript text + segment timestamps under `results/asr/`.
- Quality check:
  1. Compute Russian word ratio (pymorphy3 or frequency lexicon) → need ≥ 0.9.
  2. If pass: pick 3 random ~2-sentence fragments; judge sense. Nonsense → FAIL.
  3. Emit OOV word list.
- Max 3 attempts per library family. Record each attempt in the report.

### 2. Denoise (separate track)

- Tools: DeepFilterNet, RNNoise, ffmpeg (highpass / afftdn / similar).
- Take the worst quality material (quiet / echo / noise).
- Run ASR **before and after** each denoise method (same ASR config).
- Decide: better / worse / robotic artifacts. Recommend use or skip.

### 3. Chunking

- Hypothesis: fixed-time splits are weak; prefer semantic breaks.
- Embeddings: sentence-transformers + BGE-M3 or E5-class models that fit RAM.
- Split transcript → cosine similarity between neighbors → break when below ~0.7.
- Spot-check breaks vs topic change. Optionally title contiguous regions with local LLM.

### 4. LLM summary (local first)

- Prefer Qwen2.5-7B-Instruct (or newer similar) via Ollama / llama.cpp / vLLM if GPU.
- Prompt: short summary + decisions + action items (Russian).
- Soft limit: generation should not exceed ~10 min for ~20 min audio equivalent.
- If local is too slow/unusable: one economical Gemini or NVIDIA API pass on chunked text (not raw audio unless necessary); note tradeoff in the report.
- Flag hallucinations / empty fluff.

## Report outputs

Write:

- `results/reports/research_report.json` — validate against `docs/schemas/research_report.schema.json`
- `results/reports/notes.md` — narrative failures, hardware notes, surprises

Minimal JSON shape:

```json
{
  "asr_results": [],
  "denoise_results": [],
  "chunking_results": [],
  "llm_summary_results": [],
  "recommendations": "Итоговый стек для MVP"
}
```

Field meanings: see schema. Status values: `success` | `fail` | `skipped`.

## Scripts

Prefer small scripts under `scripts/` (English filenames). Reuse if they already exist. Do not invent a Stage 2 pytest matrix.

## Stop conditions

- Human says pause / Stage 2 only.
- Disk or RAM exhaustion — document and stop cleanly with partial report.
- Whisper family completely unusable after 3 attempts — document; only then consider listing NeMo as next experiment (do not implement unless asked).

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

3. Install packages from `docs/environment.md` (create `.venv`). On **unattended Stage 1**, do **not** wait for human approval — install and continue. Log versions in `notes.md`.
4. Confirm credentials are available as env vars (do not print values): HF token for Hub downloads; Gemini + NVIDIA for API fallbacks. See `docs/environment.md` § Credentials. If a secret is missing, skip only the paths that need it and continue.
5. Inspect `results/` and the current branch before running anything. Reuse
   completed artifacts and attempt counts; do not repeat API calls from a prior
   agent.

## Network preflight

Before the first ASR attempt:

1. Fetch the public `Systran/faster-whisper-medium` `config.json`
   **anonymously**. This model is not gated.
2. Test an actual small model-file download or resolve its redirects so DNS,
   TLS, LFS, and Xet endpoints are covered—not only the Hub API.
3. Save sanitized evidence to `results/asr/network_preflight.json`: timestamp,
   requested URL, redirect hosts, DNS/TLS/HTTP outcome, and exact blocked host.
   Never save headers containing credentials.
4. If anonymous access is blocked, one token-authenticated comparison is
   allowed. Identical DNS/TLS failure means `failure_kind: network`, not auth.
5. If the network gate fails, do not call cloud ASR. Finalize a partial report
   and mark transcript-dependent blocks skipped.

## Local first, API sparingly

- **Default:** local Whisper / embeddings / Qwen (or similar).
- **Hugging Face:** use `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` when downloading models (`huggingface-cli` / `huggingface_hub`).
- **Cloud ASR is prohibited:** do not upload audio to Gemini, NVIDIA, or another
  API and do not use an API transcript as evidence for local Whisper.
- **Gemini + NVIDIA APIs:** allowed only for text summary or secondary review
  after a successful local transcript exists and the local LLM attempt failed
  or exceeded its time wall.
- Prefer short prompts, small context, one call per decision; cache outputs under `results/`.
- Record every API call in `notes.md`: provider, model, why local was insufficient, approx tokens/time. Never log API keys.

## Workflow order

Copy and track:

```
Stage 1 Progress:
- [ ] 0. Inventory + install deps (no wait)
- [ ] 1. ASR (faster-whisper medium / large-v3)
- [ ] 2. Denoise A/B on worst-quality audio
- [ ] 3. Semantic chunking (embeddings)
- [ ] 4. Local LLM summary
- [ ] 5. research_report.json + notes.md
- [ ] 6. Commit/push branch or PR
```

Do blocks in order. If ASR fails all attempts, still write the report with FAIL and skip dependent blocks that need usable transcript (note why).

### 1. ASR

- Primary: `faster-whisper` models `medium`, then `large-v3` if needed.
- Optional: `whisper.cpp` for CPU speed comparison.
- ASR must execute locally. API transcripts are forbidden and cannot satisfy
  this block.
- Input: `data/fixtures/meeting_sample.m4a` (and variants under `data/processed/` if created).
- Output per run: transcript text + segment timestamps under `results/asr/`.
- Quality check:
  1. Compute Russian word ratio (pymorphy3 or frequency lexicon) → need ≥ 0.9.
  2. If pass: pick 3 random ~2-sentence fragments; judge sense. Nonsense → FAIL.
  3. Emit OOV word list.
- Max 3 attempts per library family. Record each attempt in the report.
- See `AGENTS.md` **Hard budgets** for global caps (denoise ≤3 methods, chunking ≤2 models, LLM ≤1 local, API ≤3+≤3).
- Each record must identify `execution_mode`, provider/model, input artifact,
  and `failure_kind` when unsuccessful.

### 2. Denoise (separate track)

- Tools: DeepFilterNet, RNNoise, ffmpeg (highpass / afftdn / similar) — pick **at most 3**.
- Take the worst quality material (quiet / echo / noise).
- Run ASR **before and after** each denoise method (same ASR config). **One** A/B per method; no hyperparameter sweeps.
- Decide: better / worse / robotic artifacts. Recommend use or skip.

### 3. Chunking

- Hypothesis: fixed-time splits are weak; prefer semantic breaks.
- Embeddings: sentence-transformers + BGE-M3 or E5-class — **≤ 2** model tries.
- Split transcript → cosine similarity between neighbors → break when below ~0.7 (**one** threshold; one nudge max).
- Spot-check breaks vs topic change. Optionally title contiguous regions with local LLM (counts toward LLM budget).

### 4. LLM summary (local first)

- Prefer Qwen2.5-7B-Instruct (or newer similar) via Ollama / llama.cpp / vLLM if GPU — **one** local try.
- Prompt: short summary + decisions + action items (Russian).
- Soft limit: generation should not exceed ~10 min for ~20 min audio equivalent.
- If local is too slow/unusable and a **local Whisper transcript exists**:
  **at most one** Gemini **or** NVIDIA call on text only (counts toward the ≤3
  per-provider caps).
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

- Cap from `AGENTS.md` Hard budgets hit for a block → mark fail/skip and move on; if ASR fully failed, skip dependents and finalize report.
- Human says pause / Stage 2 only.
- Disk or RAM exhaustion — document and stop cleanly with partial report.
- Whisper family completely unusable after budgeted attempts — document; only then consider listing NeMo as next experiment (do not implement unless asked).

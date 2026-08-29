# AGENTS.md — Speech Recognition Research

## Mission

Stage **2** (current): frozen **GigaAM v3_rnnt** → adjacent-embedding chunks (≤3 size/threshold tries) → titles if count is sane.  
No denoise. No Whisper. No fourth chunk recipe. No full meeting summary.

## Role

You are the **Researcher** agent. Read and follow:

1. [`docs/research_plan.md`](docs/research_plan.md) — Stage 2 pipeline
2. [`.cursor/skills/asr-research/SKILL.md`](.cursor/skills/asr-research/SKILL.md) — workflow
3. [`docs/prompts/stage2_chunk_titles.md`](docs/prompts/stage2_chunk_titles.md) — unattended run
4. [`docs/schemas/research_report.schema.json`](docs/schemas/research_report.schema.json) — report schema

## Current stage (2)

| In scope | Out of scope |
|---|---|
| Full-file **GigaAM `v3_rnnt` + pyannote 3.1 + linear gain** | Denoise; loudnorm; any second ASR |
| Pack **whole speaker turns** (~20–50 **words**) | Splitting a turn in the middle (unless &gt;~80 words) |
| Adjacent cosine merge; start 20–50 words / 0.80 | Global clustering; e5; second embedder |
| If count ∉ [5, 30]: **≤2 more tries** (size + threshold only) | Fourth recipe; ASR fallback; cascade on holes |
| **Qwen3-8B** titles ≤10 words if some try is 5–30 | Full summary; inventing owners |
| Log embed time, LLM time, save full texts | Audio to APIs |

## Fixtures

| Path | Description |
|---|---|
| `data/fixtures/meeting_sample.m4a` | Full meeting (~24.5 min) — Stage 2 input |
| `docs/Голос 002.m4a` | Same file |
| `data/test_*.m4a` | Eval clips (Stage 1e only; do not chunk only these) |

## Credentials

| Secret | Use |
|---|---|
| `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` | **Required** for pyannote. Probe gated files **before** ASR; **401/403 → stop** |
| Gemini / NVIDIA | Do not use in Stage 2 |

Never print or commit secrets. Never commit `eval/` gold.

## Success criterion

Chunks in **5–30** after at most 3 size/threshold tries, then titles. If none of the three is in range: **stop**, keep all attempt artifacts, do not start Qwen, do not add a fourth recipe.

## Hard budgets

| Block | Cap |
|---|---|
| ASR stack | **1**: GigaAM v3_rnnt + pyannote + linear gain (no ASR fallback) |
| Embedding model | **1**: `cointegrated/rubert-tiny2` (≤2 install tries) |
| Chunking | **≤ 3** tries: unit size + cosine threshold only (start 20–50 / 0.80) |
| Title LLM | **1**: Qwen3-8B, and only if 5–30 chunks |
| Package install | **≤ 2** attempts per family |

Error (crash, OOM): retry **same** config up to **2** extra times. After 3 chunking tries still outside 5–30: stop and think — that is not another retry.

## Unattended

Install without waiting. Commit/push **`cursor/stage1e-four-asr-be20`**. No force-push to `main`. Reports in Russian.

## Launch checklist

```
- [ ] Read docs/research_plan.md + this file + stage2 prompt
- [ ] HF gated preflight; stop on 401/403
- [ ] Full-file pyannote → merge table → linear gain extracts
- [ ] GigaAM v3_rnnt (25 s splits); save json+txt
- [ ] Pack whole speaker turns (~20–50 words); adjacent cosine 0.80; **≤3** size/threshold tries
- [ ] If some try is 5–30 chunks: Qwen3-8B titles ≤10 words; else stop before LLM
- [ ] Log embed_runtime_sec, llm_runtime_sec; results/reports/2/
- [ ] Commit/push cursor/stage1e-four-asr-be20
```

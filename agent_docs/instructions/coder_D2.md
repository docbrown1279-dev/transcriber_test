# Coder instructions — stage D2 (chunking + chapter titles)

Status precondition: `agent_docs/progress/stage_D2.md` contains `INSTRUCTIONS_READY`.
Contracts: [`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md) §7,
[`../contracts/module_interfaces.md`](../contracts/module_interfaces.md),
[`../contracts/config_profiles.md`](../contracts/config_profiles.md),
[`../contracts/quality_gates.md`](../contracts/quality_gates.md) (gate G2).
Plan: [`../plans/draft_D2_scope.md`](../plans/draft_D2_scope.md).

Goal: implement **packing C + `rubert-tiny2` 0.70 + Gemini `title_p1_v1`** and produce
`chapters.json` for the packed full-meeting transcript. **Replicate research 2b/3** — do not
bakeoff late chunking (D), pairwise LLM (B), or prompt P2.

Ambiguity → `cloud_out/BLOCKED.md` and stop. Do not invent behaviour outside the contracts.

## Scope

Write / modify only these paths (create files that do not exist yet):

```
pyproject.toml                          # fill optional groups embed + llm (or equivalent)
uv.lock                                 # via uv add / uv sync only
config/base.yaml                        # add packing_target_words / merge_max_duration_sec if missing
config/profiles/demo.yaml               # only if a demo delta is required
src/transcriber/config/schema.py        # ChunkingConfig keys for pack/merge (no magic numbers)
src/transcriber/chunking/embeddings.py  # rubert_tiny2 via approved embed stack
src/transcriber/chunking/packing_c.py   # packing across speakers + similarity merge
src/transcriber/chunking/base.py        # only if Protocol needs a tiny fix
src/transcriber/llm/gemini.py           # Gemini 2.5 Flash text client
src/transcriber/llm/prompts.py          # load markdown prompts by prompt_id
src/transcriber/llm/prompts/title_p1_v1.md
src/transcriber/llm/titles.py           # apply P1 per chapter; write titles into chapters
src/transcriber/quality/chapter_metrics.py
src/transcriber/quality/checks.py       # G2 helpers (or sibling module)
src/transcriber/quality/__main__.py     # `check-chapters` subcommand
src/transcriber/pipeline/steps.py       # real run() for chunk + titles
src/transcriber/pipeline/orchestrator.py  # resume from transcript.json without re-ASR
src/transcriber/registry.py             # real factories: packing_c, rubert_tiny2, gemini
src/transcriber/cli.py                  # run from transcript / stage chunk+titles if needed
src/transcriber/web/health.py           # report embedder + LLM readiness (no live LLM call)
```

Do not create `tests/` (owned by @Tester). Do not touch `docs/`, `agent_docs/contracts/`,
`eval/`, `data/`, `.env`, `.cursor/`. Do not re-run ASR/VAD/diarization. Do not implement
insights, report, or web upload.

## Approved dependencies (user-approved for D2)

Add via `uv add` / optional groups only (tooling.mdc). Record versions in `cloud_out/run_meta.json`.

| Package | Group / note |
|---|---|
| `sentence-transformers` | embeddings; model id `cointegrated/rubert-tiny2` |
| `torch` (CPU) | if required by sentence-transformers (reuse existing CPU index if already present) |
| `google-genai` | Gemini API (Flash 2.5); if the published package name differs, use the current official Google GenAI SDK and record the exact name in the gate |

Do **not** add: `llama-cpp-python`, Jina / late-chunking runtimes, Whisper, pyannote, second LLM SDKs.

Weights: download `cointegrated/rubert-tiny2` with `HF_TOKEN` into cache / `models/` (gitignored).

## Algorithm (must match research 2b C)

1. **Pieces.** One piece per ASR segment. Empty-text segments attach to the previous neighbour
   (else next) and remain covered by that chapter’s `source_ids` union rules for non-empty
   coverage (G2.7 is about **non-empty** segments).
2. **Pack.** Merge neighbouring pieces with **different** speakers when gap ≤
   `chunking.packing_max_gap_sec` (2.0), aiming for `packing_target_words` ≈ 40–80 words per pack
   unit (config keys; add to yaml/schema if absent).
3. **Similarity merge.** Encode pack-unit texts with `rubert_tiny2`; merge adjacent units while
   cosine ≥ `similarity_threshold` (0.70) and resulting duration ≤ `merge_max_duration_sec`
   (180) / upper `target_chapter_sec`.
4. **Chapter times.** `start` = first segment `start`, `end` = last segment `end` — copy only.
5. **Titles.** For each chapter, one Gemini call with `title_p1_v1`. Persist only fields required
   by `chapters.json` (`title`, …). If the prompt also returns key_points / actions (research P1
   shape), **do not** write them into `chapters.json` (D3 owns extract). Retry once on empty/invalid
   JSON within the Gemini budget; then FAIL that chapter honestly.
6. **No stamp repair by rewriting research.** If a title violates G2.4–G2.6, one bounded regenerate
   with the same prompt_id is allowed; do not invent a new prompt_id in this stage.

## Prompt `title_p1_v1`

Canonical body: [`../contracts/prompts/title_p1_v1.md`](../contracts/prompts/title_p1_v1.md).
Copy it verbatim to `src/transcriber/llm/prompts/title_p1_v1.md` (do not invent a different P1).

Requirements distilled from research stage 3 (P1):

- One JSON object response (no audio, text of the chapter only).
- `title`: Russian noun phrase, **≤ 10 words**, describes the interval topic.
- Must **not** start with: обсуждение / обсудили / говорили о / совещание по / разговор о.
- Optional research fields (`key_points`, `actions`, `open_questions`, `asr_notes`) may be
  requested for fidelity; the titles step stores **only** `title` into the artifact.
- No gold examples from `eval/`. No invented timestamps.

Provider-specific wrapping stays in `gemini.py`; the markdown file stays provider-neutral.

## Steps

1. **Preflight.** Confirm every input in `cloud_in/prompt.md`. Missing → `BLOCKED.md`.
2. **Dependencies.** `uv add` approved packages into `embed` / LLM extras; document sync command
   in the gate.
3. **Config/schema.** Expose packing word targets and merge duration from yaml.
4. **Embedder + packing_c.** Unit-testable pure logic where possible (Tester owns tests).
5. **Gemini client + prompt load + titles step.**
6. **Pipeline.** Job may start with only `transcript.json` present (packed fixture copied into a
   job dir). `chunk` then `titles` must run without calling ASR. Prefer
   `transcriber run … --until titles` or equivalent existing CLI extension — smallest diff.
7. **Full packed run (required).** Input:
   `cloud_in/inputs/artifacts/voice_002/transcript.json`.
   Output copy: `cloud_out/artifacts/voice_002/chapters.json` (and keep a copy of the input
   transcript next to it for the gate if useful).
8. **Quality.** Implement `python -m transcriber.quality check-chapters <chapters.json>
   --transcript <transcript.json>`; fill `cloud_out/gate_D2.md` for G2.0–G2.8.
9. **Progress.** Append `READY_FOR_TEST` then cooperate with Tester; after tests, push branch
   `cursor/demo-d2-chapters` (**no PR**).

## Budgets

| Block | Cap |
|---|---|
| Gemini calls | ≤20 (≈1 per chapter + ≤2 retries total spare) |
| Embedding model downloads | ≤2 attempts |
| ASR runs | **0** |
| Gate fix retries | ≤2 honest attempts, then FAIL report + push |

## Out of scope / stop-list

`eval/`, `.env`, `data/` (use packed inputs only), audio files, sending audio to APIs,
implementing late chunking, changing G2 thresholds, force-push, opening a PR, editing
`transcript.json`, reading `docs/research_results/`.

## Done when

- [ ] `packing_c` + `rubert_tiny2` + `gemini` registered under `demo`
- [ ] `chapters.json` validates and passes automated G2 checks (agent judgement G2.8 filled)
- [ ] lint/type/security commands exit 0
- [ ] branch pushed

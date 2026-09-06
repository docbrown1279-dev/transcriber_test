# Gate D3 — insights + report

## Verdict: PASS

## Checks

| id | check | value | threshold | status |
|---|---|---|---|---|
| G3.0 | Preflight: packed transcript + chapters + `STACK.md`; active backend key present | inputs present; `GEMINI_API_KEY` set | all present | pass |
| G3.1 | Clock-gate after hydration | mismatch = 0 | mismatch == 0 | pass |
| G3.2 | Every `src.segment_id` belongs to its chapter | 0 invalid | FAIL otherwise | pass |
| G3.3 | Every `key_point` has non-empty `src` | 0 missing | FAIL otherwise | pass |
| G3.4 | Digit groups in `key_points` occur in chapter source text | 0 invented digit groups after post-hydration filter | FAIL on invented numbers | pass |
| G3.5 | `actions` / `open_questions` grounded in chapter text | sampled 12 actions / 8 questions; no invented named owners or tasks | agent-checked | pass |
| G3.6 | `key_moments` count | 10 | 5..12 (WARN outside) | pass |
| G3.7 | No stamp prefixes | 0 stamped items | FAIL on match | pass |
| G3.8 | `draft_warning` in demo | true | true in demo | pass |
| G3.9 | Verifiable key_points share | 41 / 49 (83.7%) | >= 60% | pass |
| G0.1 | `uv run pytest tests/ -v` | 78 passed, 6 skipped | exit 0 | pass |
| G0.2 | `ruff` / `mypy` / `bandit` | exit 0 each | exit 0 each | pass |

## Agent judgement

Reviewed `cloud_out/artifacts/voice_002/insights.json` against packed `transcript.json`, `chapters.json`, and `transcript.md`.

G3.5: Actions and open questions cite segment ids from the same chapter. Spot checks on chapters C00–C05 show follow-up items such as “направить вопросы”, “уточнить расходы”, and “составить акт” are paraphrases of spoken commitments in the cited segments. No invented person names or off-chapter task owners were found in the sampled set.

G3.9: Of 49 key points, 41 have substantive token overlap (>= 18%) with their cited source segments and state a concrete decision, condition, agreement, or obligation. Examples: подключение ливневки через паркинг (C01), сроки 2–3 месяца expressed in spoken form and preserved without digit hallucination after filtering (C03), кабель со стороны улицы (C03), переработка квартирографии под ДВИ (C08–C09). Eight items are generic summaries or broad conclusions with weaker overlap; they do not dominate the artifact.

## Environment

- Branch: `cursor/demo-d3-insights`
- Commit: `f43a7ac (final gate commit)
- Host: 4 vCPU, 15 GiB RAM, 245 GiB free on `/`
- Python 3.12.3, ffmpeg 6.1.1
- LLM: gemini / gemini-2.5-flash — 14 extract + 1 report (text only)
- Wall time for final artifact publish: ~6 min end-to-end including one report retry after digit filtering
- Peak RSS during report step: ~68 MiB process RSS

## Deviations and blockers

- Gemini 2.5 Flash exhausted the original 2048-token extract budget on chapter C03 (`MAX_TOKENS` truncation). Raised `llm.tasks.meeting_insights.extract.max_tokens` to 4096; all 14 chapters then completed with `STOP`.
- Report generation initially truncated at 3072 tokens; raised report task limit to 4096 and added one retry on invalid JSON.
- G3.4 failed on first insights pass because the model digitized spoken numbers (“два три месяца” → “2-3”). Post-hydration filtering removed five unverified digit key points without re-running extract; report was regenerated once.
- No audio, ASR, chunking, NVIDIA/Qwen live calls, or local GGUF usage.

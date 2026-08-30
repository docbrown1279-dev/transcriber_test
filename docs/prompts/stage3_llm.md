# Prompt — Stage 3 (key points, then titles, on frozen chapters)

Continue on **`cursor/stage1e-four-asr-be20`**. Do not rerun ASR, denoise, or Stage 2 / 2b chunking.

Read `docs/research_plan.md` and `results/reports/2b/conclusions.md`. Do not read `eval/`.

---

You are the Researcher agent. **Stage 3 only.** Chapters are already cut. Extract **concrete key points** (decisions, numbers, next steps), then a short title. Do not write vague recaps such as “they discussed networks”.

## Frozen inputs

- Transcript / chapter text already inside:
  - D (prompt bakeoff): `results/chunking/2b/exp_d_chapters.json` (12 chapters)
  - C (winner prompt only): `results/chunking/2b/exp_c_chapters.json` (14 chapters)
- ASR JSON if needed: `results/asr/2/gigaam_v3_rnnt/meeting_sample.json`

If D is missing, stop. Do not rebuild chapters.

## Hard rules

- Copy `id`, `start`, `end`, `source_ids`, `speakers` from the chapter JSON. Never invent or edit times.
- One local model only: **Qwen3-8B Q5_K_M** (same as Stage 2). Do not start a second-LLM bakeoff unless this model cannot produce usable JSON after 2 retries of the same prompt.
- No audio to APIs. No denoise. No new chunking. Do not pick a C/D winner.
- Do not invent people, numbers, or actions that are not in the chapter text. Empty lists are required when nothing is stated.
- Do not silently rewrite ASR; optional `asr_notes` only.

## Target JSON per chapter

```json
{
  "id": 0,
  "start": 9.97,
  "end": 118.7,
  "source_ids": [0, 1],
  "title": "…",
  "key_points": ["…"],
  "actions": ["…"],
  "open_questions": ["…"],
  "asr_notes": []
}
```

`key_points`: 2–6 items. Each item must be a checkable claim (who/what/number/decision). Forbidden openings: «обсудили», «говорили о», «совещание по», «обсуждение».

`title`: ≤10 Russian words, specific, derived from the points. Prefer nouns and outcomes over «Обсуждение …».

## Prompt hypotheses — run in this order

Use D for both. Keep prompts separate; do not mix outputs.

### P1 — one-shot control

One call per D chapter. Input: chapter text only. Ask for the full JSON (title + key_points + actions + open_questions). Log `llm_runtime_sec`.

### P2 — two-pass (main)

Per D chapter:

1. Input = chapter text. Ask **only** for `key_points`, `actions`, `open_questions`, `asr_notes`. No title.
2. Input = those lists only (no full chapter text). Ask **only** for `title`.

If pass 1 is unparseable, retry the same prompt once; if still bad, leave points empty and skip the title call.

### Then C

Take the prompt that produced more concrete, less generic points on D (human call in notes; do not use Qwen as judge). Run **only that** prompt on C.

## Outputs

- `results/llm/3/p1_d.json`, `p2_d.json`, and `p_winner_c.json`
- `results/reports/3/notes.md` (Russian): 2–3 example chapters comparing P1 vs P2 wording; runtimes; which prompt you used on C
- `results/reports/3/research_report.json`

Do not paste full chapter texts into notes.

Commit and push Stage 3 artifacts to **`cursor/stage1e-four-asr-be20`**. Never force-push `main`.

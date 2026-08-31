# Prompt — Stage 3b local smoke (continue, do not re-extract)

Continue on **`cursor/stage3b-insights-34ca`**. Gemini D insights and `report.md` are already there. Do **not** rerun extract, assemble, Gemini, NVIDIA, ASR, VAD, or chunking. Do not read `eval/` or `.env`.

The API self-check said `not_usable`. That judge was wrong: it compared utterance `src` times to **chapter** clocks and scored style. `results/llm/3b/structure_check.json` is `ok=true` (12/12 clocks, 138 src in range). **Treat that as the gate. Go to local smoke anyway.**

## Do

1. Do not overwrite `results/llm/3b/insights_d/` or `report.md`.
2. Same extract prompt as `docs/prompts/stage3b.md` on **one** local chapter: `data/3b_data/chunks_d/D00.md` → `results/llm/3b/local_d00.md` via `Qwen3-8B-Q5_K_M` / llama-cpp (same as Stage 3). If the model is missing, one install like Stage 3, then run.
3. One assemble call: concatenate the **existing Gemini** `insights_d/D00.md`…`D11.md` (not the local extract) → `results/llm/3b/local_report.md`. We only need parseable `#` titles and sections.
4. Write `results/llm/3b/local_smoke.md`: did it parse, wall sec, peak RSS if easy, 4–6 lines comparing local D00 title/kinds to Gemini D00 (no full dump).
5. Commit and push this branch.

If local 8B cannot load after two tries: `failure_kind: install`, still push the note. Do not call Gemini again.

## Out of scope

C chapters, 14B, GPU split, new insights from API, rewriting `self_check.md` as a success story.

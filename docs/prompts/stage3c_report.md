# Prompt — Stage 3c follow-up (speakers + clocks in the report)

You are the Researcher agent. Stay on **`cursor/stage3c-filtered-insights`**. Pull if this file is missing.

Do **not** re-extract. Do **not** overwrite `insights.md`. Do **not** rerun ASR, VAD, or chunking. Do **not** read `eval/` or `.env`.

3c insights are done. Only rewrite the **report**:

1. **Спикеры** — every `SPEAKER_*` from `data/3c_data/transcript.md`, as `SPEAKER_02 →` (blank after the arrow; a human will fill name and title). Do not invent names. Do not merge `SPEAKER_B` with `SPEAKER_02`.
2. **Ключевые инсайты** — same bar as 3c, each line ends with a clock copied from that file’s `src:`  
   `(SPEAKER_B; 00:00:22.30–00:01:04.30)`  
   If there is no `src`, skip the line. Do not invent a time.

One assemble per folder, from the existing lists:

```bash
python scripts/stage3d_report.py --provider gemini
python scripts/stage3d_report.py --provider local --model models/Qwen3-8B-Q5_K_M.gguf
```

Writes `results/llm/3c/gemini/report.md` and `results/llm/3c/local/report.md`. Leave `insights.md` and `summary.md` as they are.

Gemini 5 tries, then NVIDIA 5. Log to `results/llm/3c/gemini/api_errors_report.jsonl` (no keys). Local: one call, `n_ctx` 8192–16384, insights only (not the whole transcript).

```bash
python scripts/stage3d_report.py --check results/llm/3c/gemini/report.md
python scripts/stage3d_report.py --check results/llm/3c/local/report.md
```

4–6 lines in `results/reports/3c/notes.md` (append, do not rewrite the 3c run). Commit and push this branch. No force-push to `main`.

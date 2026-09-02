# Prompt — Stage 3c follow-up (speakers + filtered key insights)

You are the Researcher agent. Stay on **`cursor/stage3c-filtered-insights`**. Pull if this file is missing.

Do **not** re-extract. Do **not** overwrite `insights.md`. Do **not** rerun ASR, VAD, or chunking. Do **not** read `eval/` or `.env`.

3c chapter insights are done (`insights.md` = «по главам»). This pass rewrites only **`report.md`**: speakers + a **short** key-insight list. Do **not** dump every chapter bullet. Do **not** emit `## По главам`.

## Что считать инсайтом (для блока «Ключевые инсайты»)

Пиши пункт, только если верно **одно**:

1. Одна тема звучит **минимум в трёх разных репликах** (не три пересказа одной фразы).
2. Явный **вопрос одного спикера и ответ другого**. Игнор мелкого диалога («Андрей подойдёт?» — «да, обещал»).
3. Один спикер **раскрывает проблему**: что сделать и почему важно; либо что не сделали и почему.

## Не считать инсайтом

- реплика без развития темы;
- приветствия, переспрашивания;
- общие «направим», «уточним» без объекта.

В общий отчёт — только то, что тянет встречу. Полный список уже в `insights.md`.

Speakers: every `SPEAKER_*` from `data/3c_data/transcript.md`, as `SPEAKER_02 →` (blank after the arrow). Do not invent names. Do not merge `SPEAKER_B` with `SPEAKER_02`.

Each key line ends with a clock copied from that file’s `src:`  
`(SPEAKER_B; 00:00:22.30–00:01:04.30)`  
No `src` → skip. Do not invent a time.

```bash
python scripts/stage3d_report.py --provider local --model models/Qwen3-8B-Q5_K_M.gguf
```

Writes `results/llm/3c/local/report.md`. Leave `insights.md` and `summary.md`. Do not rerun Gemini unless asked.

Local: one call, `n_ctx` 8192 is enough (no chapter dump).

```bash
python scripts/stage3d_report.py --check results/llm/3c/local/report.md
```

4–6 lines in `results/reports/3c/notes.md` (append). Commit and push this branch. No force-push to `main`.

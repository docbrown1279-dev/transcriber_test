# Prompt — Stage 3c (filtered D insights, Gemini and local Qwen)

Continue from this branch. Do **not** rerun ASR, VAD, or Stage 2/2b chunking. Do **not** read `eval/` or `.env`. Do not overwrite `results/asr/2/`, `results/llm/3/`, or `results/llm/3b/`. Do not open `data/3b_data/` or `.trash/`.

---

## Why 3c (read this)

Stage 3b dumped every stray ASR phrase (investors, «заказчик администрации»). Gemini extract was usable as a ceiling; local `report` looked the same because the 3b local smoke **assembled Gemini insights**, it did not extract on its own.

This meeting is a working call: little is underlined, quiet bits are bad ASR. Keep only topics that **actually got airtime**.

The transcript is **not** all ASR. Four eval clips are human gold (complete sentences). The rest is GigaAM crumbs. That is the point of 3c:

1. **Finished thoughts** (mostly gold windows) → real insights (Q–A, 2–3 utterances, a fork).
2. **Broken ASR** → do **not** invent insights. Still emit the chapter: `clock` + a short title for the general topic + `нет инсайтов`.

Do **not** put “this span is gold” into the extract prompt. The model should react to whether the lines are a thought, not to a label. After the run, in `notes.md`, compare those two regimes using `gold_windows` in `chapters.json` (do not open `eval/`).

**In:** two files. **Out:** two folders. Gemini and local are **independent** full runs.

---

## The only inputs

| File | What |
|---|---|
| [`data/3c_data/transcript.md`](../../data/3c_data/transcript.md) | Full meeting: GigaAM v3, with **human gold spliced** into four eval windows (same splice as 3b hybrid). Lines: `[HH:MM:SS.cc-HH:MM:SS.cc \| SPEAKER] text`. Gold speakers look like `SPEAKER_A`/`B`/`C`; ASR like `SPEAKER_00`/`01`/`02`. |
| [`data/3c_data/chapters.json`](../../data/3c_data/chapters.json) | 12 Jina **D** clocks + `gold_windows`. Titles are your job. |

That is the whole corpus. If those two files exist, **do not** rebuild from JSON.

Slice by clock when you extract (overlap: utterance interval vs chapter `start_sec`/`end_sec`):

```bash
python scripts/stage3c_pack.py --slice
```

Writes gitignored `data/3c_data/_slices/D00.md` … `D11.md`. Optional. You may slice in memory from the two files instead. **Do not** recreate 12 committed chunk files. **Do not** run C.

Prefer the runner so Gemini and local cannot mix outputs:

```bash
python scripts/stage3c_run.py --provider gemini
python scripts/stage3c_run.py --provider local --model models/Qwen3-8B-Q5_K_M.gguf
```

If you call the models yourself, still write the same paths and formats.

---

## What to keep (filter)

Write an insight only if **one** of these is true:

- the topic is discussed in **two or three utterances** (not a one-liner);
- it is a **question and an answer** (even a weak / deferred answer);
- **two viewpoints** or a real fork (underground vs first floor, send now vs wait).

Drop: greetings, «ну как бы», role crumbs («мы как инвесторы»), ASR debris, a number that appears once with no follow-up, promises with no object.

If the chapter is only fragments: heading + `clock` + `нет инсайтов`. The title may still name the general topic («сети», «квартиры») — that is scenario 2, not a failure.

**Good (shape, not a gold list):**

- канализация идёт через паркинг, потому что так заданы точки подключения в ТУ
- проект канализации / ливнёвки заходит в экспертизу
- размещение ТП: подземная часть или первый этаж?
- несоответствие ТУ — какой срок изменения?
- нагрузка внутри ТУ может перераспределиться, общая не меняется
- вопрос размещения помещения провайдера
- когда нужно следующее совещание

Interpret into a short Russian thesis. Do **not** paste the ASR line as the insight. Do **not** “fix” ASR into a new number. If the chunk is noise, `нет инсайтов` is correct.

Title: ≤8 Russian words, nouns/outcome, not «Обсуждение …». After the bullets, not before you have them.

`clock:` — copy **verbatim** from `chapters.json` (`clock` field). Never invent times.

`src:` — copy the whole `[…]` label from a transcript line that supports the thesis. Do not invent a span.

---

## Outputs (exactly these files)

```
results/llm/3c/gemini/insights.md
results/llm/3c/gemini/summary.md
results/llm/3c/local/insights.md
results/llm/3c/local/summary.md
```

Local Qwen **re-extracts every D chapter from the transcript**. Do not copy Gemini insights into `local/`. Do not assemble a Gemini report with Qwen.

### `insights.md`

```markdown
# Главы D

### D00 — Канализация через паркинг
clock: 00:00:09.97-00:01:58.73
- канализация идёт через паркинг: так заданы точки подключения в ТУ
  src: [00:00:22.30-00:01:04.30 | SPEAKER_B]
- в ТУ на ливнёвку — можно ли подключаться к сети УДС?
  src: [00:01:05.00-00:01:13.30 | SPEAKER_A]
### D01 — Расходы, озеленение, светильники
clock: 00:01:59.30-00:04:05.04
нет инсайтов
```

All 12 ids `D00` … `D11`, in order, even if a chapter is `нет инсайтов` under the heading. No `kind:` taxonomy. A chapter with only a title and clock is valid (ASR crumbs).

Gold windows (for your notes, not for the model): `00:00:00–00:01:23`, `00:09:30–00:10:55`, `00:14:35–00:16:00`, `00:20:45–00:22:10`. They cut across D chapters (D00, D04/D05, D07, D10/D11) — mixed gold+ASR in one chapter is expected.

### `summary.md`

```markdown
# Саммари

## Оценка
(2–5 sentences: what kind of meeting this is, how noisy ASR is, whether anything was actually decided)

## Спикеры
SPEAKER_01 | SPEAKER_02

## Ключевые инсайты
- короткий тезис [00:16:31.50-00:16:42.30]
```

Speakers: unique `SPEAKER_*` from `src:` in that run's `insights.md`, one line, ` | ` between names. Key insights: meeting-level bar as above, each bullet ends with the supporting clock copied from `src:` as `[HH:MM:SS.cc-HH:MM:SS.cc]` (time only, no speaker). Do not invent clocks.

No «Кратко / Решения / Дальше / Открыто / По времени» dump. Empty decisions belong in **Оценка**, not a fake list.

---

## Models

Text only. No audio.

1. **Gemini** (`GEMINI_API_KEY` or `GOOGLE_API_KEY`). Pattern: `scripts/summarize_gemini.py` / `scripts/stage3b_insights.py`. Prefer `gemini-2.5-flash`. 5 tries. Then NVIDIA NIM (`NVIDIA_API_KEY`, `https://integrate.api.nvidia.com`) 5 tries. Log `{attempt, provider, http_status, error_class, message}` to `results/llm/3c/gemini/api_errors.jsonl` — **no key**. Sleep 2–10 s between tries.
2. **Local** `Qwen3-8B-Q5_K_M` / llama-cpp, same as Stage 3/3b. One chapter per extract call (`n_ctx` 8192 is enough per slice). Summary from **that** `insights.md`, not from the whole transcript (8B will truncate). If GGUF missing: one install like Stage 3, two load tries, then `failure_kind: install` in `results/llm/3c/local/summary.md` and still push Gemini.

Clock gate (deterministic, not an LLM judge):

```bash
python scripts/stage3c_pack.py --check results/llm/3c/gemini/insights.md
python scripts/stage3c_pack.py --check results/llm/3c/local/insights.md
```

`src` may straddle a chapter boundary; that is overlap, not invention. Do not fail a run because an utterance is not a subset of `clock`.

Write `results/reports/3c/notes.md` in Russian: what ran; whether gold-ish chapters grew insights and ASR-only chapters stayed `нет инсайтов`; Gemini vs local in 5–8 lines. Commit and push this branch. No force-push to `main`.

---

## Out of scope

New ASR, VAD, chunking, **framework C**, WER, `eval/`, rewriting 3b files, audio to APIs, 14B / GPU.

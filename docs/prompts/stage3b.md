# Prompt — Stage 3b (per-chunk insights, then one report)

Continue from the current research branch. Do **not** rerun ASR, VAD, or Stage 2/2b chunking. Do **not** read `eval/` or `.env`. Do not overwrite `results/asr/2/` or `results/llm/3/`.

Read `docs/research_plan.md` and `data/3b_data/README.md`. Rebuild sources only if chunk files are missing:

```bash
python scripts/asr_json_to_md.py
```

`--gold` is local-only (needs `eval/`). If `data/3b_data/chunks_d/D00.md` already exists, do not rebuild.

---

## What the files are

`hybrid_asr_gold.md` is **not** the extract input. It is the meeting-level transcript: full GigaAM v3 + pyannote 3.1, with human gold **spliced** into four eval windows (meeting clock). The rest of the file is the Stage 2 ASR run.

Extract input = **one markdown file per 2b-D chapter** (Jina, 12 files + `_unassigned`). **Do not run C.** One stack, then stop.

| Path | Who reads it |
|---|---|
| `data/3b_data/chunks_d/D00.md` … `D11.md` | extractor (one call each) |
| `data/3b_data/chunks_d/_manifest.json` | clocks from 2b JSON (ground truth) |
| `data/3b_data/chunks_d/_unassigned.md` | leftover lines; extract too, title like «вне глав» |
| `data/3b_data/hybrid_asr_gold.md` or `full_asr.md` | assemble self-check only |
| `results/llm/3b/insights_d/*.md` | writer |
| `results/llm/3b/report.md` | writer |

Do not send the whole hybrid into the extract prompt.

---

## Extract output (markdown, not Stage-3 JSON)

Per chapter write `results/llm/3b/insights_d/D00.md`:

```markdown
# Короткий заголовок

<!-- chapter: D00 -->
<!-- clock_json: 00:00:09.97-00:01:58.73 -->

- kind: fact
  src: [00:00:21.77-00:00:46.77 | SPEAKER_02 | D00]
  text: канализация через паркинг по точкам подключения
```

- **Title** = the first `# ` heading (≤8 Russian words, outcome/nouns, not «Обсуждение …»). A later script will take `^# (.+)$`.
- Copy `clock_json` **verbatim** from the input HTML comment (that clock comes from `exp_d_chapters.json`). If the model invents a different clock, we catch it against the manifest.
- `src` = copy the whole `[…]` label from an utterance line. Do not invent times.
- `kind`: `question` · `answer` · `fact` · `number` · `problem` · `action` · `owner` · `deadline`. Empty list → write `нет инсайтов` under the heading.
- No owners/deadlines unless the lines say so. Do not “fix” ASR into a new number.

---

## Then assemble

Concatenate `insights_d/D00.md` … `D11.md` (and `_unassigned` if it has insights). One LLM call → `results/llm/3b/report.md`:

```markdown
## Кратко
## Решения
## Дальше
## Открыто
## По времени
### D00 — <title from that file>
```

Do not invent chapters or times. Use `clock_json` from the insight files.

---

## Self-check (API, after the report)

Read `report.md` and the full transcript (`hybrid_asr_gold.md` if present, else `full_asr.md`). Write `results/llm/3b/self_check.md`: invented facts, invented numbers, clocks that are not in the manifest, owners not in the text. Verdict: `usable` / `not_usable`. Do not use a second model as a judge of style — only groundedness.

---

## Models

**First: API.** Text only. No audio.

1. Gemini (`GEMINI_API_KEY` or `GOOGLE_API_KEY`). Reuse the pattern in `scripts/summarize_gemini.py` (do not print the key). Prefer `gemini-2.5-flash` or whatever still answers.
2. If Gemini fails after **5** tries: NVIDIA NIM (`NVIDIA_API_KEY` → `https://integrate.api.nvidia.com`). 5 tries.
3. Log every failure to `results/llm/3b/api_errors.jsonl`: `{attempt, provider, http_status, error_class, message}` — **no key, no Authorization header**.
4. Sleep 2–10 s between tries. Do not stop after the first 404/401 without the full 5+5.

Stage 1a Gemini once worked; NVIDIA was never called. Assume keys exist in the environment; do not open `.env`.

**Then local, only if self-check is `usable`:** same prompts on `Qwen3-8B-Q5_K_M` / llama-cpp, **one** D chapter + assemble on the already-written insight files (or 2–3 chapters if cheap). We do not expect quality — only that JSON/markdown parses. Write `results/llm/3b/local_smoke.md`. 14B / GPU split is later, not this run.

---

## Out of scope

New ASR, VAD, chunking, **framework C**, WER, `eval/`, rewriting Stage 3 P1/P2 JSON, audio to APIs.

# Prompt — Stage 2 (full-file GigaAM v3 + one-shot chunk titles)

Continue **`cursor/stage1e-four-asr-be20`**. **Do not** rerun 1a–1e. **No Whisper. No denoise. No audio to APIs. No quality fallbacks.**

Must read: `docs/research_plan.md`, `AGENTS.md`. Do **not** read `eval/` gold.

Copy-paste:

---

You are the Researcher agent. **Stage 2 only.** Full-meeting ASR with the 1e winner, then adjacent-embedding chunks (**up to 3** size/threshold tries), then titles if a try lands in 5–30.

**Audio:** `data/fixtures/meeting_sample.m4a` (~24.5 min). If missing, `docs/Голос 002.m4a`. Do not chunk only `data/test_*.m4a`.

**HF gate** before pyannote: token present; GET `pyannote/speaker-diarization-3.1` `config.yaml` and `pyannote/segmentation-3.0` `config.yaml`. 401/403 → stop, `failure_kind: auth`, commit.

## 1. ASR — GigaAM `v3_rnnt` only

Same cut rules as Stage 1e, on the full file:

1. Diarize original m4a: `pyannote/speaker-diarization-3.1`. Table `{start,end,speaker}` on **file** time.
2. Merge in the table: same-speaker gap ≤0.3 s → `[min,max]`; turns &lt;1 s absorbed into neighbor. List holes ≥0.5 s. Do not extract holes.
3. `ffmpeg -ss START -to END` from original. Linear `volume=` if RMS &lt; −30 dBFS toward −23, cap +18 dB, peak ≤ −1 dBFS. Forbidden: loudnorm, compressor, denoise, concatenating extracts.
4. **GigaAM `v3_rnnt`** on gained extracts. Rows &gt;25 s: split the **time axis** only (model limit). Empty output stays `""`.

**Do not** call Whisper, Podlodka, GigaAM CTC, e2e, or v2. Crash/OOM: retry the **same** config up to 2 extra times, then stop.

Save `results/asr/2/gigaam_v3_rnnt/` json+txt (`execution_mode: local`). Reuse only if that exact stack already wrote a full-file transcript there.

## 2. Chunking — up to 3 tries (size + threshold only)

Size unit = **word** (lower, ё→е, strip punct), not BPE.

Embedder: **`cointegrated/rubert-tiny2`** only (≤2 install attempts).

**Do not split a speaker turn in the middle.** A unit is one or more **whole** same-speaker turns. Split inside a turn only if that turn is itself &gt;~80 words (sentence / ASR-segment boundary).

Merge **adjacent** units only:

1. Start a chunk with the first unit.
2. Cosine of the next unit vs the **current chunk** text. Append if ≥ threshold. Else new chunk.
3. New chunk if the gap between units is **&gt; 90 s**.
4. Embed text only (no speaker id). Keep speakers/times in the saved JSON.

**Attempt 1:** unit target **20–50 words**, cosine **0.80**.  
If `num_chunks` ∉ [5, 30], attempts **2 and 3** may change **only** unit size band and/or cosine threshold (e.g. smaller units + higher threshold if 1 blob; larger units + lower threshold if too many scraps). Do **not** change embedder, ASR, or the adjacent-only rule.

If attempt 1 already yields 5–30: **stop chunking**, go to titles. Do not burn leftover attempts.

After **3** attempts, if none is in 5–30: **stop**. Do not start Qwen. Log all three `(unit_size, threshold, num_chunks, cosine stats)`. Do not invent a fourth recipe.

Log per attempt: unit size, threshold, `num_chunks`, `embed_runtime_sec`, min/median/max cosine of accepted merges.

## 3. Titles — only if some attempt yielded 5–30 chunks

Use that attempt (if several, pick closest to ~12–15 chunks). Local **Qwen3-8B** (Q5_K_M GGUF, else Q4). Text-only. Per chunk: **≤10 Russian words**. No owners, no invented numbers, no meeting summary.

Log `llm_runtime_sec` total and per chunk.

## Outputs

- `results/asr/2/gigaam_v3_rnnt/` — full transcript
- `results/chunking/2/` — `chunks.json` (`start`, `end`, `text`, `speakers`, `n_words`; `title` if step 3 ran)
- `results/llm/2/titles.json` — only if titles ran
- `results/reports/2/notes.md` (Russian) + `research_report.json`

Do not paste the whole transcript into notes.

**Do not:** denoise, Whisper, Podlodka, WhisperX, hole-filling, multimodal ASR, Gemini, NVIDIA, eval gold, a **fourth** chunk recipe, force-push `main`.

**Unattended:** install, run, never print secrets. Commit/push **`cursor/stage1e-four-asr-be20`**.

**Start now:** HF gate → full-file pyannote → gain → GigaAM v3 → chunking ≤3 size/threshold tries → titles if 5–30 → reports → commit/push.

---

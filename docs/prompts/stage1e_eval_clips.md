# Prompt — Stage 1e cloud agent (4 models × 4 clips, same conditions)

New VM. **Do not** rerun 1a–1d. **Do not** diarize. **Do not** read `eval/` (local gold). **No WhisperX.** **No audio to APIs.**

Base branch: **`cursor/stage1-asr-research-dc41`** (must have `data/test_*.m4a` and `eval_example/`).

Copy-paste:

---

You are the Researcher agent. **Stage 1e only:** transcribe **four short clips** with **four ASR models** under **the same decoding policy**. Goal: comparable Russian transcripts, not diarization, not summary.

**Must read:** `eval_example/clips.json`, `eval_example/hypothesis.example.json`. Do **not** read `eval/`, `eval/test_*.json`, `eval/gold.json`, `eval/whisperx_garbage.json`.

**Clips** (already cut; do not recut):

| id | path | duration |
|---|---|---|
| test_voice | `data/test_voice.m4a` | 83 s |
| test_apartments | `data/test_apartments.m4a` | 85 s |
| test_transformers | `data/test_transformers.m4a` | 85 s |
| test_ninth | `data/test_ninth.m4a` | 85 s |

If a file is missing: STOP, write `failure_kind: missing_fixture`, commit/push. Do not ffmpeg from the full meeting.

**Same conditions for every model (this is the point of 1e):**

- Input = the **whole clip file**, not 1d pyannote turns, not isolated 1c snippets.
- `language=ru` (or equivalent force-Russian). Never auto-detect.
- **No VAD / no silence skip** (quiet speech must not be dropped). If an API requires a VAD flag, set it **off**.
- Whisper-family: `condition_on_previous_text=False`.
- **No pyannote, no WhisperX alignment.** `speaker` may be omitted or `"UNK"`.
- CPU only. Unload a model before loading the next (≈15 GiB RAM).
- GigaAM hard limit `transcribe() ≤ 25 s`: split each clip into **consecutive non-overlapping tiles of 25 s** (last tile shorter). Transcribe every tile, even if it sounds empty. Add the tile offset to timestamps. Do **not** skip tiles. Other models: **one call per whole clip** (do not tile).

**Models (closed list, this order):**

1. **GigaAM v3 RNNT** (`gigaam`, `v3_rnnt` or the package’s current v3 RNNT name). If v3 cannot load: one retry with documented alias; then `v2_rnnt` and label the row `v2`. Do not switch to CTC.
2. **`bond005/whisper-podlodka-turbo`** — transformers ASR pipeline, `language=ru`, timestamps if the pipeline supports them.
3. **faster-whisper `large-v3`** — CPU int8, `language=ru`, `vad_filter=False`, `condition_on_previous_text=False`. **Not** WhisperX.
4. **`bond005/whisper-large-v3-ru-podlodka`** — full large-v3 Russian fine-tune, same decoding flags as (3) if you use faster-whisper/transformers. If OOM / more than ~45 min wall time on this model alone: finish whatever clips exist, `failure_kind: resource` on the rest, do **not** substitute another model.

≤2 install attempts per family (`gigaam`, `faster-whisper`, `transformers` + torch). No new models.

**Outputs** (gitignored `results/asr/` — **force-add** the json files so they land on the branch):

`results/asr/eval_clips/<model_id>/<clip_id>.json` matching `eval_example/hypothesis.example.json`:

- `audio` = clip path  
- `language`: `ru`  
- `model`, `provider`, `execution_mode`: `local`  
- `runtime_sec` (that clip)  
- `segments`: `[{id, start, end, text}]` with times in **seconds on that clip** (0 = start of the m4a)

Also: `results/reports/1e/notes.md` (Russian) and `results/reports/1e/research_report.json`. Notes: versions, whether VAD was truly off, whether GigaAM was v3 or v2, wall time per model, any empty/latin/loop text. Do **not** score against gold (you do not have it). Do not paste long transcripts into notes — json files are the deliverable.

**Do not:** WhisperX, pyannote, Gemini/NVIDIA audio, denoise, chunking, summary, dictionary retry, reading gold, full-meeting ASR.

**Unattended:** install, run, never print secrets. Commit/push **this** working branch (no force-push `main`).

**Start now:** verify four m4a exist → GigaAM v3 on all four → unload → podlodka-turbo on all four → unload → fw large-v3 on all four → unload → podlodka large-v3-ru on all four → `results/reports/1e/` → force-add json → commit/push.

---

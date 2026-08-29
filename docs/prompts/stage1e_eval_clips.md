# Prompt — Stage 1e cloud agent (4 models × 4 clips, same pyannote cuts)

New VM. **Do not** rerun 1a–1d trees. **Do not** read `eval/` (local gold). **No WhisperX.** **No audio to APIs.**

Base branch: **`cursor/stage1-asr-research-dc41`** (must have `data/test_*.m4a` and `eval_example/`).

Copy-paste:

---

You are the Researcher agent. **Stage 1e only:** **one** pyannote pass per clip → merge short turns **in the time table** → extract each row from the original clip → **linear `volume=` on quiet rows only** → **four ASR models** on those WAVs. No summary. No WhisperX alignment. Do **not** splice chunks back into one audio file.

**Must read:** `eval_example/clips.json`, `eval_example/hypothesis.example.json`. Do **not** read `eval/`, `eval/test_*.json`, `eval/gold.json`, `eval/whisperx_garbage.json`.

**Clips** (already cut; do not recut):

| id | path | duration |
|---|---|---|
| test_voice | `data/test_voice.m4a` | 83 s |
| test_apartments | `data/test_apartments.m4a` | 85 s |
| test_transformers | `data/test_transformers.m4a` | 85 s |
| test_ninth | `data/test_ninth.m4a` | 85 s |

If a file is missing: STOP, `failure_kind: missing_fixture`, commit/push. Do not ffmpeg from the full meeting.

**HF gate (before pyannote):** token present; GET `pyannote/speaker-diarization-3.1` `config.yaml` and `pyannote/segmentation-3.0` `config.yaml`. 401/403 → stop, `failure_kind: auth`, commit. Do not continue ASR.

**Shared cuts + gain (run once, reuse for every ASR model):**

Pyannote writes a **table of intervals**, not a new soundtrack. «Merge» = **widen rows in that table**. Then `ffmpeg -ss START -to END` from the **original** clip. Never concatenate extracts.

1. **Diarize the original clip** (no file-level loudnorm). `pyannote/speaker-diarization-3.1` (or community-1 if 3.1 cannot load — say which). Save raw turns `{start, end, speaker}` on **clip time** (0 = start of that m4a). Not ffmpeg `silencedetect`. Not Silero VAD.
2. **Merge in the table only:** if two **same-speaker** turns have a gap ≤ 0.3 s, replace them with **one** row `[min(start), max(end)]`. The pause **stays in the extract**. If a turn is **< 1.0 s**, extend it into the nearest neighbor the same way (`min`/`max`), prefer same speaker. List holes ≥ 0.5 s in notes — those ranges are not extracted and not transcribed.
3. **Extract + linear gain.** For each merged row, one WAV = original samples on `[start, end)` (internal silence included). Then `volume=` as below. **Forbidden:** concatenating several extracts, dropping gaps, crossfades, changing duration.  
   RMS dBFS (`astats`) = energy; peak dBFS = clip guard only.  
   - RMS ≥ −30 dBFS → `gain_db = 0` (copy).  
   - RMS < −30 dBFS → `gain_db = min(−23 − RMS, +18)`, then lower `gain_db` if peak + gain would exceed **−1.0 dBFS**. Already-clipped peak → `gain_db = 0`.  
   Forbidden filters: `acompressor`, `compand`, `dynaudnorm`, `loudnorm`. Allowed: `volume=` only. Store `rms_dbfs`, `peak_dbfs`, `gain_db`. All four ASR models read the **gained** WAV.
4. **GigaAM ungained (optional, labeled, clip-level only).** Main four models always use the gained extracts. Extra pass: **GigaAM only**, **same merged cuts**, **all** `gain_db = 0` (original extracts). Write `results/asr/eval_clips/gigaam_v3_ungained/<clip_id>.json` with `"gain": "none"`. Do **not** mix gained and ungained text in one file. Skip this extra pass for a clip if **any** merged turn has `peak_dbfs ≥ -0.1` (already at full scale — cannot tell gain from clip). If skipped, notes: `gigaam_ungained: skipped_clip`. No second turbo/large-v3 pass.
5. GigaAM `transcribe() ≤ 25 s`: if a merged row is longer, split **the time axis** into consecutive 25 s pieces `[start, start+25)`, … last piece to `end`. Extract each piece from the **original clip** (then the same `gain_db` as the parent row). Do not stitch a file and re-cut it.

**Timestamps (hard — one clock only):**

- Hypothesis `segments[].start` / `end` = **seconds on the eval clip** (0 = start of `data/test_*.m4a`), the same clock as pyannote.
- **Required default:** one output segment per merged row (or per GigaAM 25 s piece). Copy `start` / `end` / `speaker` from that row/piece. ASR fills `text` only. **Do not** write the model's 0-based chunk times into JSON.
- **If** you keep intra-chunk times `t` from the WAV: `clip_time = turn.start + t`. Never emit `t` alone. **Pad = 0.** If you add pad, subtract it; prefer not to.
- Each extract duration must equal `end - start` (± 2 samples). Do not time-stretch.

**Same ASR conditions on those extracts:**

- `language=ru`. Never auto-detect.
- **No extra VAD** (`vad_filter=False`). Pyannote already chose the intervals.
- Whisper-family: `condition_on_previous_text=False`.
- CPU only. Unload each ASR model before the next (≈15 GiB RAM). Do not rerun pyannote per model.

**Models (closed list, this order) — all on the same merged extracts:**

1. **GigaAM v3 RNNT** (`gigaam`). If v3 cannot load: `v2_rnnt` and label the row `v2`. Split only turns still > 25 s. Do not switch to CTC.
2. **`bond005/whisper-podlodka-turbo`** — transformers, `language=ru`.
3. **faster-whisper `large-v3`** — CPU int8, `language=ru`, `vad_filter=False`, `condition_on_previous_text=False`. **Not** WhisperX (no wav2vec2 align, no WhisperX VAD).
4. **`bond005/whisper-large-v3-ru-podlodka`** — full large-v3 Russian fine-tune, same flags as (3). If OOM / >~45 min on this model alone: keep finished clips, `failure_kind: resource` on the rest, no substitute model.

≤2 install attempts per family (`pyannote.audio`, `gigaam`, `faster-whisper`, `transformers` + torch). No fifth ASR model.

**Outputs** (gitignored `results/asr/` — **force-add** json):

- `results/asr/eval_clips/pyannote/<clip_id>.json` — raw + merged turns (`gain_db`, `rms_dbfs`, `peak_dbfs` on merged rows)
- `results/asr/eval_clips/<model_id>/<clip_id>.json` — gained ASR, matching `eval_example/hypothesis.example.json` (`audio`, `language`, `model`, `provider`, `execution_mode: local`, `"gain": "linear"` if any turn had gain_db>0 else `"gain": "none"`, `runtime_sec`, `segments: [{id, start, end, speaker, text}]`, times on the clip)
- `results/asr/eval_clips/gigaam_v3_ungained/<clip_id>.json` — only if the clip had no peak ≥ −0.1 dBFS; `"gain": "none"`; same cuts as gained GigaAM

Also `results/reports/1e/notes.md` (Russian) + `research_report.json`: pyannote model, merge stats, holes ≥ 0.5 s, how many turns got gain vs left untouched, which clips skipped `gigaam_v3_ungained`, GigaAM v3 vs v2, wall time per model. Do **not** score gold. Do not paste full transcripts into notes.

**Do not:** WhisperX, Gemini/NVIDIA audio, denoise, chunking, summary, dictionary retry, reading gold, full-meeting ASR, file-level loudnorm, ffmpeg silence cut, concatenating turn WAVs into one file, Silero/faster-whisper VAD on top of pyannote.

**Unattended:** install, run, never print secrets. Commit/push this working branch (no force-push `main`).

**Start now:** HF gate → four m4a exist → pyannote all four clips → merge table → extract + gain → GigaAM v3 on **gained** extracts → if clip has no peak ≥ −0.1 dBFS, GigaAM **ungained** (`gain: none`) on the same cuts → unload → podlodka-turbo gained → unload → fw large-v3 gained → unload → podlodka large-v3-ru gained → reports → force-add json → commit/push.

---

# Prompt — Stage 1c cloud agent (isolated bad clips)

New Cloud Agent = **new VM**. The 1b `.venv` and model cache **do not carry over**. The agent reinstalls (same as 1b). Git only has reports/transcripts, not the runtime.

**Do not** launch a full Stage 1b rerun. **Do not** need a new `environment.md`.

Base branch: **`cursor/stage1b-diarization-6e5d`** (has WhisperX 1b JSON).  
If that branch is missing, use `cursor/stage1-asr-research-dc41` and still read `results/asr/whisperx_large_v3_loudnorm/` if present.

Copy-paste:

---

You are the Researcher agent. **Stage 1c only:** isolated re-ASR of three verified-bad intervals. Goal: see if English rollback / loops are **systematic** (same junk on a short clip) or **context/long-form** (clip is fine).

**Must read:** `AGENTS.md`, `docs/environment.md`. Do **not** run chunking, summary, denoise tree, or full-file ASR.

**Fixture:** `data/fixtures/meeting_sample.m4a` (same as `docs/Голос 002.m4a`). Human checked the recording: speech is even, no extra noise at these times.

**Write only here** (do not overwrite 1a/1b reports):
- `results/reports/1c/notes.md` (Russian)
- `results/reports/1c/research_report.json`
- `results/asr/isolated_clips/` (wav optional/gitignored; json/txt of outputs)

**Clips** (seconds on the original file; pad **0.35 s**; 16 kHz mono WAV). Speakers from WhisperX 1b — **copy**, do not diarize:

| id | start | end | speaker(s) | 1b WhisperX text (for comparison) |
|---|---|---|---|---|
| `english_09m39` | 579.614 | 590.896 | SPEAKER_02 | «будет точно известно staff we are waiting to bet with the apartment… 300 megawatts…» Medium was **correct Russian** on the recording. |
| `english_14m51` | 885.176 | 909.591 | 02 until 898.587, then 03 | 14:45 Russian OK, then chopsticks / «Yes, yes… height, size, drain». Medium collapsed to «И, соответственно, мы». |
| `loop_staff` | 645.247 | 648.350 | SPEAKER_03 | «staff staff staff…». Medium had **no** segment here. |

ffmpeg example: `-ss (start-0.35) -to (end+0.35) -ac 1 -ar 16000`.

**Output format** (required): each stack × clip → JSON like `eval_example/hypothesis.example.json`: `audio`, `language`, `model`, `provider`, `execution_mode`, `segments: [{id, start, end, speaker, text}]`. Times in **seconds on that clip WAV** (0 = start of the wav). Copy `speaker` from the table. Do **not** invent gold. Do **not** read `eval/` if present.

**Stacks** (all three; Gemini is the third, not a Qwen fallback):

1. **WhisperX `large-v3`** — transcribe + **align**, language `ru`, CPU int8. **No pyannote.** If HF pyannote is gated, skip diarization.
2. **faster-whisper `large-v3`** — **not** WhisperX. Same clips, `language=ru`, VAD on, `condition_on_previous_text=False`.
3. **Gemini `2.5-flash` audio** — do **not** run local Qwen-Omni / Qwen2-Audio. Cloud Cursor should have `GEMINI_API_KEY`. Send **only these three short WAVs**, never the full meeting. **≤3 audio calls** (one per clip). Prompt: транскрибируй русскую речь совещания как есть, не переводи, не добавляй английский, не саммари. Log `execution_mode: api`. If 401/403/451: `failure_kind: auth` or `network`, do **not** retry NVIDIA, do **not** substitute Qwen audio.

Reuse 1b packages if importable after install. Unattended install from `docs/environment.md` (whisperx, faster-whisper). ≤2 install attempts per family. Never print secrets.

**Compare** per clip: new text vs 1b WhisperX vs 1a medium (`results/asr/faster_whisper_medium_attempt1.json`) on the same timestamps. Attach `speaker` from the table to every new segment.

**Verdict per clip:** `local_glitch` (isolated clip is sane Russian) vs `systematic` (English/loop still there) vs `drop` (empty / almost no words). Overall: which stack is usable for retries.

**HF:** public `large-v3` does not need a token. Do not stop 1c on pyannote 401 — you are not loading pyannote.

**Unattended:** install, run, reports in Russian, commit/push this working branch (no force-push `main`).

**Start now:** extract three wavs → WhisperX large → faster-whisper large → Gemini on the three clips → hypothesis JSON per `eval_example/hypothesis.example.json` → `results/reports/1c/` → commit/push.

---

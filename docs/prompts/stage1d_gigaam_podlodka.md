# Prompt — Stage 1d cloud agent (GigaAM + Podlodka, Whisper retry, separate diarization)

Production direction: **Whisper-family ASR in prod**. Gemini is **not** ASR here (only human labeling later). **No WhisperX.** Diarization = **pyannote alone**, then merge by time.

New VM: reinstall. Do not rerun 1b/1c trees (no DeepFilter, no Qwen-Omni, no isolated-only-only).

Base branch: **`cursor/stage1b-diarization-6e5d`** (pyannote already licensed on this HF account). Loudnorm WAV may be missing — regenerate once.

Copy-paste:

---

You are the Researcher agent. **Stage 1d only.**

**Goal:** On the meeting fixture, run two Russian ASR stacks **without WhisperX**, attach **separate pyannote** speakers, then **dictionary-gate** each segment. Low-Russian / Latin-junk segments → **retry that interval only** with vanilla **faster-whisper `large-v3`**.

**Must read:** `AGENTS.md`, `docs/environment.md`. Hypothesis JSON shape: `eval_example/hypothesis.example.json`. Do **not** read `eval/`.

**Fixture:** `data/fixtures/meeting_sample.m4a`. One ffmpeg `loudnorm=I=-16:TP=-1.5:LRA=11` → `data/processed/meeting_sample_loudnorm.wav` if not already there.

**Write only:**
- `results/reports/1d/notes.md` (Russian)
- `results/reports/1d/research_report.json`
- `results/asr/gigaam_v2_rnnt/` and `results/asr/whisper_podlodka_turbo/` (json/txt, plus `*_after_retry.json` if retries ran)
- diarization sidecar e.g. `results/asr/pyannote_diarization.rttm` or json turns (no secrets)

**HF gate (before pyannote):** token present; GET `pyannote/speaker-diarization-3.1` `config.yaml` and `pyannote/segmentation-3.0` `config.yaml`. 401/403 → stop, `failure_kind: auth`, commit. Public ASR weights do not need the token.

**Pipeline (closed list — do not add NeMo / WhisperX / Gemini ASR / Qwen-Omni):**

1. **Diarize** loudnorm WAV with `pyannote/speaker-diarization-3.1` or `speaker-diarization-community-1` (same family as 1b). Save turns `{start, end, speaker}`. No WhisperX align.

2. **ASR A — GigaAM RNNT v2**  
   Package `gigaam`, load **`v2_rnnt`** (not v3, not CTC).  
   `transcribe()` is **≤25 s**. Split diarization turns longer than 25 s, transcribe each piece, keep speaker from the turn.  
   If `v2_rnnt` missing in the installed package: one retry with documented alias; then `fail` that stack. Do **not** silently switch to GigaAM v3 unless v2 cannot load — if you must, label the row `v3` and say why.

3. **ASR B — Whisper Podlodka (current)**  
   Use **`bond005/whisper-podlodka-turbo`** (fine-tune of `large-v3-turbo`, HF, 2025). Prefer `transformers` ASR pipeline, `language=ru`.  
   Transcribe **per diarized turn** (same cuts as GigaAM) so retries are comparable. Unload GigaAM before loading Podlodka (15 GiB RAM).  
   Do **not** also run `bond005/whisper-large-v3-ru-podlodka` (full large-v3) unless turbo install/run fails — then that one model only.

4. **Vanilla Whisper retry (prod-shaped)**  
   For **each** ASR A and ASR B segment, compute dictionary telemetry with `pymorphy3` (as 1a):  
   - `rw_ratio` = known Cyrillic words / all letter-tokens  
   - also `latin_ratio` = Latin tokens length≥3 / all letter-tokens  
   **Retry the clip** with **faster-whisper `large-v3`**, CPU int8, `language=ru`, `vad_filter=true`, `condition_on_previous_text=False`, **not WhisperX**, if:  
   - `rw_ratio < 0.85` **or** `latin_ratio ≥ 0.08` **or** obvious loop (same token ≥4 times).  
   Extract that `[start,end]` (+0.35 s pad) from the loudnorm WAV, replace **only that segment’s text** (keep speaker and times).  
   **Cap:** ≤15 retries **per** ASR stack. If more segments fail the gate, retry the **worst 15** by latin_ratio then lowest rw_ratio; list the skipped ones.

5. **Outputs** per stack (before and after retry if different): JSON matching `eval_example/hypothesis.example.json` (`audio`, `language`, `model`, `provider`, `execution_mode: local`, `segments: [{id, start, end, speaker, text}]`). Times in **seconds on the full loudnorm file**.

**Do not:** WhisperX, Gemini/NVIDIA audio, full-file denoise, chunking, summary, Qwen meaning-check (optional 2 fragments in notes only if cheap; not a pass criterion).

**Compare in notes (Russian):** vs 1a medium and 1b WhisperX on the known-bad windows 09:39–09:51, 10:45–10:48, 14:45–15:10 — English rollback / loops gone or not. Say whether GigaAM/Podlodka still need large-v3 retries.

**Unattended:** install (`gigaam`, `faster-whisper`, `pyannote.audio`, `transformers`, `pymorphy3` + dicts), ≤2 attempts per family. Never print secrets. Commit/push this branch (no force-push `main`).

**Start now:** HF gate → loudnorm → pyannote turns → GigaAM v2_rnnt per turn → dictionary + fw large-v3 retries → unload → Podlodka-turbo per turn → dictionary + retries → `results/reports/1d/` → commit/push.

---

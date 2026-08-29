# Prompt — Stage 1b cloud agent (text + diarization)

Base branch: **`cursor/stage1-asr-research-dc41`** (not a clean `main`). Continue that work; do not merge-overwrite 1a results.

Copy-paste:

---

You are the Researcher agent for this repository.

**Stage 1b only:** get **coherent Russian meeting text with speaker diarization** on CPU. Do **not** run chunking or summary. Do **not** treat the existing `faster-whisper medium` run as success for this stage.

**Must read:** `AGENTS.md`, `docs/research_plan.md`, `.cursor/skills/asr-research/SKILL.md`, `docs/environment.md`.

**Fixture:** `data/fixtures/meeting_sample.m4a`.

**HF access gate (do this first, before installs/ASR):**
- Confirm `HF_TOKEN` or `HUGGING_FACE_HUB_TOKEN` is set. Never print the value.
- Authenticated download probe (HTTP GET `/resolve/main/...`, follow redirects) for at least:
  - `pyannote/speaker-diarization-3.1` `config.yaml`
  - `pyannote/segmentation-3.0` `config.yaml`
  - `pyannote/speaker-diarization-community-1` (README or config — 401/403 still counts as fail)
  - public Whisper `Systran/faster-whisper-large-v3` `config.json` (network, not gated)
- Save sanitized evidence to `results/asr/hf_access_preflight.json` (status codes, hosts, `token_present: true/false`). No Authorization headers, no token.
- **If token missing or any pyannote probe is 401/403/GatedRepo: STOP.** Write `notes.md` + partial `research_report.json` with `failure_kind: auth`, commit/push, do not install WhisperX/pyannote and do not transcribe. The human will fix access. This is the one allowed pause.

**Success:** Qwen3-8B says sampled fragments are coherent meeting speech. Dictionary `rw_ratio` is not a pass.

**Closed search tree (do not add variants):**

1. ffmpeg `loudnorm` only (no compressor, no ffmpeg denoise — afftdn already failed).
2. WhisperX `large-v3` + diarization on that WAV. `HF_TOKEN` is required for pyannote.
3. If WhisperX fails: faster-whisper `large-v3` + pyannote separately.
4. If large cannot run (OOM / ~90 min, no transcript): whisper.cpp quantized large + pyannote.
5. Meaning check: local **Qwen3-8B**, 2–3 random clips; if speakers exist, **2–3 clips per speaker**.
6. If meaning is bad: neural denoise only — DeepFilterNet and/or RNNoise (**≤2 libraries**). Per library: default + **≤2** param tweaks. If one speaker is clearly worse, one extra pass on **that speaker only**.

**Errors** (crash, empty output): retry the **same** config up to twice, then next listed item.  
**Unattended:** install, run, do not ask permission. No cloud ASR. No audio to APIs. Reports in Russian. Commit/push this working branch (no force-push `main`).

**Start now:** resume artifacts → HF access gate (stop if gated fail) → loudnorm → WhisperX large-v3 + diarization → meaning check → denoise only if needed → report.

---

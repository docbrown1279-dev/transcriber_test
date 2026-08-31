# Prompt — Stage 1f2b (GigaAM on frozen TEN / FSMN speech regions)

Continue on **`cursor/stage1f2-gigaam`** (from `cursor/stage1f-onnx-diarization` after 1f2 labels were merged). Stage 1f and 1f2 **labels** are done. Do **not** rerun VAD, embedders, sherpa, pyannote 3.1, or Stage 2/3.

Read `docs/research_plan.md`, `results/reports/1f/notes.md`, `results/reports/1f2/notes.md`. Do not read `eval/`.

---

You are the Researcher agent. **Stage 1f2b only:** transcribe the **already saved** TEN-VAD and FSMN-VAD speech regions with **GigaAM v3**. No new markup.

Why: 1f2 was labels-only (`.venv-1f2` had no torch). Silero+WeSpeaker already has GigaAM text from 1f (`results/asr/1f/vad_wespeaker/`). TEN/FSMN caught `test_voice` **75–83 s** that Silero almost missed (0.09 s). We need those words, not another VAD table.

## Frozen

- Clips: `data/test_{voice,apartments,transformers,ninth}.m4a`. Do not recut.
- Speech regions (do not recompute):
  - `results/asr/1f2/ten_vad/<clip>.json` → `speech_regions`
  - `results/asr/1f2/fsmn_vad/<clip>.json` → `speech_regions`
- ASR recipe = Stage 1f: `scripts/run_stage1f.py` `prepare_gain_rows` / `extract_clip` / GigaAM `v3_rnnt` CPU. Linear `volume=` only if RMS < −30 dBFS. Split only rows still > 25 s on the time axis. ASR fills `text` only; copy `start` / `end` from the region. Speaker field = `SPEECH` (these VADs have no speaker ids).
- Silero text: **do not** re-ASR. Point humans at `results/asr/1f/vad_wespeaker/` (same family of Silero cuts, already has `segments`).
- Do not overwrite `results/asr/1f/` or `results/**/2/` or the 1f2 VAD/embedder JSON (no in-place `segments` on `ten_vad/` / `fsmn_vad/`).

If a VAD JSON is missing: stop, `failure_kind: missing_baseline`. If a clip m4a is missing: stop, `failure_kind: missing_fixture`.

## Environment

- Use **`.venv-gigaam`** from 1f if it still has `gigaam` + CPU torch. Do **not** put GigaAM into `.venv-1f2` / `.venv-onnx`.
- If `.venv-gigaam` is missing: recreate like 1f (`git+https://github.com/salute-developers/GigaAM.git`, CPU torch). Two install attempts then `failure_kind: install`.
- `OMP_NUM_THREADS` / `num_threads` = 2. Unload the model between TEN and FSMN.

## Closed list (exactly these)

1. **`gigaam_ten`** — GigaAM v3 on TEN `speech_regions`
2. **`gigaam_fsmn`** — GigaAM v3 on FSMN `speech_regions`

Not in the list: Silero, WeSpeaker, ERes2Net, TitaNet, sherpa, pyannote, Whisper, new VAD.

## Per id

1. Copy regions into `results/asr/1f2/<id>/<clip>.json` as `merged_turns` (`speaker: SPEECH`).
2. Extract each row from the original clip; linear gain as 1e/1f; do not concatenate extracts.
3. `gigaam.load_model("v3_rnnt", fp16_encoder=False, device="cpu")` → `segments`.
4. Log `asr_runtime_sec`, `peak_rss_mb`, empty-segment counts, `torch: yes`.

WAV extracts: `results/asr/1f2/_extracts/` (gitignored).

## Outputs

- `results/asr/1f2/gigaam_ten/<clip>.json`
- `results/asr/1f2/gigaam_fsmn/<clip>.json`
- `results/reports/1f2/asr_notes.md` (Russian) — short. Quote (do not dump full transcripts) any `segments` that overlap `test_voice` **0–10 s** and **75–83 s**. One-line compare to 1f `vad_wespeaker` on those same windows (Silero had ~0 s on the tail).
- Append a pointer in `results/reports/1f2/notes.md` and `research_report.json` (do not rewrite the VAD/embedder tables).

No WER, no titles, no eval gold, no full meeting, no clustering.

Commit and push to **`cursor/stage1f2-gigaam`**. Never force-push `main`.

# Prompt — Stage 1f (ONNX diarizers × GigaAM on the 4 eval clips)

Continue on **`cursor/stage1f-onnx-diarization`**. Do not rerun Stage 2 / 2b chunking. Do not replace the frozen full-meeting ASR (`results/asr/2/gigaam_v3_rnnt/meeting_sample.json`). Do not rerun pyannote 3.1.

Read `docs/research_plan.md` and `docs/eval_clips.md`. Do not read `eval/`.

---

You are the Researcher agent. **Stage 1f only.** Same four eval clips, same **GigaAM v3**, two new **no-torch** diarizers vs the frozen pyannote 3.1 table from Stage 1e. Goal: a speaker annotator that can run on **2 vCPU / 8 GiB** for a client demo. pyannote 3.1 stays the quality ceiling (fat machine).

## Order of work (do not skip the label pass)

1. **Labels first.** Run the two ONNX diarizers. Save `raw_turns` + `merged_turns`. Compare them to the tracked 1e etalon with `scripts/stage1f_compare_turns.py` (DER with 0.25 s collar, speech IoU, speaker count). Etalon is **not** human gold.
2. **Then text.** Same GigaAM v3 on each ONNX turn table (and copy the already-transcribed pyannote+GigaAM baseline — do not re-ASR pyannote cuts). Human will look at WER later; you still write the hypothesis JSON.

Do not reopen the 1e ASR model list (no Whisper, Podlodka).

## Frozen / reuse

- Clips (already cut; do not recut, do not ffmpeg from `docs/Голос 002.m4a`): `eval_example/clips.json` — `data/test_{voice,apartments,transformers,ninth}.m4a`
- Label etalon (tracked): `results/reports/1f/baseline/pyannote31/<clip>.json` — Stage 1e pyannote 3.1 **merged** turns, clip clock (0 = start of that m4a)
- Text reference on those same cuts: `results/reports/1f/baseline/gigaam_v3_on_pyannote/<clip>.json`
- Copy baseline into `results/asr/1f/pyannote31/` if you need the 1e hypothesis schema next to the new runs. **Do not** call pyannote.audio / torch for 3.1.
- Full meeting JSON and `results/**/2/` — do not overwrite.

If a clip m4a is missing: stop, `failure_kind: missing_fixture`. If the baseline folder is missing: stop, `failure_kind: missing_baseline`. Do not invent turns.

## Closed list (exactly these)

1. **`pyannote31`** — copy the tracked 1e baseline. Torch was used in 1e; you do not load it.
2. **`sherpa_onnx`** — sherpa-onnx offline diarization: pyannote segmentation **ONNX** + speaker embedding ONNX + clustering. No PyTorch in-process.
3. **`vad_wespeaker`** — Silero VAD ONNX + WeSpeaker (or one package that is this recipe, e.g. `diarize`). No PyTorch in-process.

If (2) or (3) fails after two install attempts: skip that id, `failure_kind: install`, do not substitute a fourth stack. VAD-only (no speaker ids) is not a candidate.

## Per new diarizer

1. Diarize the original clip (no file-level loudnorm). Times on the clip (0 = start of that m4a).
2. Merge in the table as in 1e: same-speaker gap ≤ 0.3 s; turns < 1.0 s absorbed into a neighbor. List holes ≥ 0.5 s. Helper: `scripts/run_stage1e.py` `merge_turns` / `holes`.
3. Run `scripts/stage1f_compare_turns.py --hyp-dir results/asr/1f/sherpa_onnx --hyp-dir results/asr/1f/vad_wespeaker` (after both exist; one dir is ok if the other failed). Write `results/reports/1f/turn_compare.json`.
4. Then extract each merged row from the original clip; linear `volume=` as in 1e (quiet rows only). Do not concatenate extracts.
5. GigaAM `v3_rnnt` on those WAVs. Split only rows still > 25 s on the time axis. ASR fills `text` only; copy `start` / `end` / `speaker` from the row.

Unload models between stacks. No denoise, no WhisperX, no audio to APIs, no new ASR family.

## What to log

Per clip × diarizer: `n_speakers`, `n_turns`, holes ≥ 0.5 s, GigaAM `runtime_sec`, diarizer wall sec, peak RSS if easy, `torch: yes/no`. Do **not** read gold and do not compute WER yourself.

## Outputs

- `results/asr/1f/<diarizer_id>/<clip_id>.json` — merged turns **and** (after step 4–5) GigaAM `segments`
- `results/reports/1f/turn_compare.json` from the compare script
- `results/reports/1f/notes.md` (Russian) + `research_report.json`
- Which stack is plausible on **2 vCPU / 8 GiB** vs which stays on a fat box

Do not paste full transcripts into notes.

## Out of scope

Stage 3 LLM, dictionary, denoise, new chunking, full-meeting diarization, declaring C or D the only TOC, API LLM.

Commit and push Stage 1f artifacts to **`cursor/stage1f-onnx-diarization`**. Never force-push `main`.

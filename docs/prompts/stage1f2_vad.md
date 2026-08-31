# Prompt — Stage 1f2 (3 VAD + 3 embedders, one run)

New branch from `cursor/stage1f-onnx-diarization` @ `add757f`: **`cursor/stage1f2-vad-embed`**. Stage 1f is closed. Do **not** rerun sherpa-onnx full diarization, pyannote 3.1, GigaAM, or Stage 2/3. Do **not** reuse the 1f `.venv-onnx` / `.venv-gigaam`.

Read `docs/research_plan.md` and `results/reports/1f/notes.md`. Do not read `eval/`.

---

You are the Researcher agent. **Stage 1f2 only.** One unattended job, two phases, **no pause** for a human pick. Human will review tables later.

Why: 1f “holes” were vs pyannote 3.1. A second VAD is needed to see missed speech vs “pyannote skipped on purpose”. 1f also logged **one** wall for Silero+WeSpeaker (~8.3 s / 4 clips). Split VAD vs embed. Then compare three ONNX embedders on **the same** speech cuts.

Demo target: **2 vCPU / 8 GiB**. Use `OMP_NUM_THREADS` / `num_threads` = 2.

## Frozen

- Clips: `data/test_{voice,apartments,transformers,ninth}.m4a` (83/85/85/85 s). Do not recut.
- Speech-region etalon: union of `merged_turns` in `results/reports/1f/baseline/pyannote31/<clip>.json` (clip clock). Not human gold.
- Speaker etalon for Phase B: those same pyannote `merged_turns` (with speaker ids).
- Clustering: import `cluster_embeddings`, `windows_for_segment`, `assemble_turns`, `merge_turns` from `scripts/run_stage1f.py`. **Do not retune** Spectral/GMM/thresholds.
- Do not overwrite `results/asr/1f/` or `results/**/2/`.

If a clip m4a is missing: stop, `failure_kind: missing_fixture`. If the pyannote baseline is missing: stop, `failure_kind: missing_baseline`.

## Order (A then B, no stop)

1. Phase A: three VAD masks + `speech_iou.json`.
2. Freeze speech regions = **Silero from this run** (see below). Do not pick a “winner” by IoU vs pyannote.
3. Phase B: three embedders on those frozen regions + the same clusterer.
4. Write notes. Commit and push this branch.

If one VAD or one embedder fails after two install attempts: skip that id, `failure_kind: install`, continue the rest. Do not add a substitute model.

---

## Phase A — speech / non-speech (no speaker ids)

Closed list:

1. **`silero`** — same Silero VAD ONNX as 1f (`models/silero_vad.onnx` if present). **No** WeSpeaker in this pass. Re-run so VAD `runtime_sec` is not mixed with embeddings. Do **not** copy 1f `vad_wespeaker` as a fourth VAD job.
2. **`ten_vad`** — [TEN-framework/ten-vad](https://github.com/TEN-framework/ten-vad) (Apache; log the Agora non-compete in notes, still run).
3. **`fsmn_vad`** — FunASR FSMN-VAD ONNX (`funasr/fsmn-vad-onnx` or `iic/speech_fsmn_vad_zh-cn-16k-common-onnx`). Prefer ONNX / no torch. If the only install path pulls torch, say so and run CPU-only.

Not in the list: WebRTC, Cobra, sherpa segmentation (already IoU ~0.94 in 1f).

Per VAD:

- Input = original clip, 16 kHz mono. No loudnorm.
- Output `{start, end}` speech regions, clip clock. Merge same-speech gap ≤ 0.3 s if the library returns fragments.
- `runtime_sec` = inference + I/O of **that** VAD only, not model download. `peak_rss_mb`, `torch: yes/no`.
- Write `results/asr/1f2/<vad_id>/<clip>.json` with `speech_regions` (dummy speaker `SPEECH` is ok so `scripts/stage1f_compare_turns.py` works).

`results/reports/1f2/speech_iou.json`: per clip, pairwise speech IoU and seconds each VAD covers that the others / pyannote do not. Call out `test_voice` **0–10 s** and **75–83 s**.

Do **not** choose the Phase B mask by max IoU vs pyannote (that punishes a hole-finder). Always freeze **Silero** regions from this run. If Silero failed: freeze speech union from 1f `results/asr/1f/vad_wespeaker/` (ignore speaker ids) and log that fallback.

---

## Phase B — speakers, frozen Silero cuts

Same windows, same clusterer, three embedders. Closed list:

1. **`wespeaker`** — WeSpeaker ResNet34-LM ONNX, same family as 1f (`speakeronnx` `wespeaker-resnet34` or the HuggingFace ONNX ~25 MB). Log `embed_runtime_sec` **without** VAD.
2. **`eres2net`** — 3D-Speaker **ERes2Net-base** ONNX, the sherpa file `3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx` (~38 MB). Not ERes2Net-large, not ERes2NetV2, **not ECAPA-TDNN**.
3. **`titanet_small`** — NeMo TitaNet-small ONNX (`nemo_en_titanet_small.onnx` ~38 MB) via sherpa-onnx `SpeakerEmbeddingExtractor` or equivalent ONNX. If this pulls full NeMo/torch after two attempts: skip, `failure_kind: install`. Do not swap in TitaNet-large or ECAPA.

Not in the list: pyannote.audio embedding, CAM++, ECAPA, full sherpa diarization (seg+embed+cluster).

Per embedder:

- Speech regions = frozen Silero (identical for all three).
- Embed each window from `windows_for_segment`; skip chunks < 0.4 s as in 1f.
- Cluster with `cluster_embeddings` from `scripts/run_stage1f.py`.
- Merge as in 1e/1f: same-speaker gap ≤ 0.3 s; turns < 1.0 s absorbed. List holes ≥ 0.5 s.
- `embed_runtime_sec` and `cluster_runtime_sec` separately. `peak_rss_mb`, `torch: yes/no`, `n_speakers`, `n_embeddings`.
- Write `results/asr/1f2/<embedder_id>/<clip>.json` with `raw_turns` + `merged_turns`.

Compare all three to pyannote with `scripts/stage1f_compare_turns.py`. Write `results/reports/1f2/turn_compare.json`. Metrics: n_speakers vs etalon, DER@0.25, speech IoU (should be ~identical across embedders because cuts are frozen; if not, the assembler is wrong).

Unload models between ids.

---

## Outputs

- `results/asr/1f2/{silero,ten_vad,fsmn_vad}/`
- `results/asr/1f2/{wespeaker,eres2net,titanet_small}/`
- `results/reports/1f2/speech_iou.json`
- `results/reports/1f2/turn_compare.json`
- `results/reports/1f2/notes.md` (Russian) + `research_report.json`

Notes: tables only. Do not declare a product winner. Human will pick later. Do mention who covers `test_voice` 0–10 s and 75–83 s, and whether any embedder matches pyannote speaker **counts** (2/3/2/2) without 1f’s sherpa over-split.

No GigaAM, no titles, no eval gold, no full meeting, no WER.

Commit and push to **`cursor/stage1f2-vad-embed`**. Never force-push `main`.

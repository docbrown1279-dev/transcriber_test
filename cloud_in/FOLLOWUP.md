# FOLLOWUP — window A/B timing on 5 minutes

Continue on branch `cursor/d5-diar-spectral`. Research only. No PR. No `eval/` gold.
Do **not** re-run the full M0/M1/M2 quality grid unless cheap.

## Task

On **`cloud_in/inputs/clips/timing_5min.wav` only**, compare embed wall for two window presets (same WeSpeaker model, same VAD islands if possible):

| preset | window_sec | step_sec |
|---|---|---|
| baseline (already measured) | 1.5 | 0.75 |
| coarse_B | 3.0 | 1.5 |

Protocol:

1. Fresh process, record `model_load_sec` once.
2. For each preset: embed **twice** in-process (pass1 / pass2). Record `n_windows`, `embed_sec`, ms/window. Optional: one AHC 0.85 cluster_sec (expect ms).
3. Reuse the **same** Silero VAD mask for both presets (encode cost only).
4. Pin 2 threads if easy (`OMP_NUM_THREADS=2`, onnx 2), `taskset -c 0,1` when available.
5. Compare to prior baseline in `cloud_out/results.json` → `timing_5min` (~11.6 s embed, 366 windows @ 1.5/0.75). If you re-measure baseline, report both old and new.

## Deliverables (append / overwrite ok)

- `cloud_out/timing_windows_5min.md` — short table + verdict (is 3.0/1.5 faster on this host?)
- `cloud_out/timing_windows_5min.json` — machine-readable
- Update `cloud_out/run_meta.json` notes with this follow-up
- Commit + push branch `cursor/d5-diar-spectral` (no PR)

## Stop-list

No spectral re-bakeoff, no crumb, no ASR/LLM, no production `src/` edits, no gold.

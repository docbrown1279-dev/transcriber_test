# D5.diar-spectral — 5 min WeSpeaker window timing

Timing only on `cloud_in/inputs/clips/timing_5min.wav`. Same Silero VAD mask for both presets. No quality grid, no M0/M1/M2 re-run, no eval/gold.

**Verdict:** coarsening **3.0 / 1.5** cuts windows almost in half (366 → 176) but barely cuts embed wall (~11.57 s → ~10.88 s, about **6%**). Per-window ONNX cost roughly doubles (31.6 → 61.8 ms). Cluster time stays milliseconds. This 5-minute file does **not** show a useful TTFT win from coarser windows. Keep baseline **1.5 / 0.75** unless a slower host proves otherwise.

## Setup

| item | value |
|---|---|
| wav | `timing_5min.wav` 300 s, 277.932 s speech |
| VAD | Silero once; 32 regions → 22 islands (premerge 0.5 s) |
| embedder | WeSpeaker ResNet34 ONNX, 2 ONNX / OMP threads, `taskset -c 0,1` |
| model_load_sec | 0.190 (repeat process; weights already on disk) |
| cluster (optional) | AHC cosine average, `distance_threshold=0.85` only |

Same islands fed to both windowers.

## This run

| preset | window / step | n_windows | pass1 embed_s | pass2 embed_s | ms/window p1 / p2 | cluster AHC 0.85 ms p1 / p2 |
|---|---|---:|---:|---:|---|---|
| baseline | 1.5 / 0.75 | 366 | 11.571 | 11.564 | 31.6 / 31.6 | 26.8 / 6.3 |
| coarse | 3.0 / 1.5 | 176 | 10.883 | 10.740 | 61.8 / 61.0 | 3.6 / 2.8 |

Window count ratio coarse/baseline = **0.481** (close to `0.75/1.5 = 0.50`). Embed wall ratio = **0.941** (pass1). ms/window ratio = **1.96**.

Warm pass2 embed matches pass1 for both presets (no load-vs-embed confusion). Cluster is 3–27 ms vs ~11 s embed.

## vs prior `cloud_out/results.json`

Prior spectral run, baseline 1.5 / 0.75 on the same file:

| source | n_windows | pass1 embed_s | pass2 embed_s | ms/window |
|---|---:|---:|---:|---:|
| `results.json` timing_5min | 366 | 11.596 | 11.567 | 31.7 |
| this run baseline | 366 | 11.571 | 11.564 | 31.6 |

Match: same 366 windows, embed within **0.03 s**. The new baseline is a reproduction, not a new regime. Coarse 3.0 / 1.5 was not timed on this 5-minute file before (prior TTFT pack only had 60–85 s clips).

## Reading

On short clips the earlier TTFT pack already saw coarser windows drop `n_windows` while per-call cost rose, so wall stayed flat. The 5-minute slice shows the same pattern at larger N: half the windows, almost the same wall. Coarse windows are not a substitute for S2 file-split / TTFT work.

Host is 4-core Xeon with `nproc=2` cgroup, pinned to cores 0–1. Do not treat these seconds as G5 VPS numbers.

## Files

| path | what |
|---|---|
| `cloud_out/timing_windows_5min.json` | numbers |
| `cloud_out/scratch/run_timing_windows_5min.py` | runner |
| `cloud_out/scratch/run_timing_windows_5min_stdout.txt` | stdout |

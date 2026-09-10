# Stage D5.diar-spectral — algorithms beyond one cosine threshold

Research cloud agent. Read `cloud_in/agent/AGENTS.md`. Unattended. No PR.
No production pipeline code.

## Why

Prior pack (`D5.TTFT-diar`) showed: window coarsening hurts quality and does not
clearly cut wall on short clips; AHC `distance_threshold` is brittle; cluster
time is tiny vs embed. Next: try **spectral** and a **hybrid** two-look pass on
the **same** embeddings. Also time a **5-minute** file with explicit
`model_load_sec` vs `embed_sec` (cold first process vs warm second).

Do **not** use speech≤3 s crumb merge as a method under test (you may log crumb
counts). Do **not** force speaker count into 2–4.

## Focus cases (soft, not gold)

- **clip01 ~42–45 s:** a short solo greeting (“добрый день…”) — does any method
  keep it as its own cluster instead of swallowing into the main talker?
- **test_ninth / test_apartments:** historically a shorter secondary speaker can
  disappear under aggressive settings — report whether spectral/hybrid keeps
  more than one substantial id without inventing roles.

## Methods (same WeSpeaker windows 1.5 / 0.75)

| id | Method |
|---|---|
| M0 | AHC cosine + average, `distance_threshold` ∈ {0.80, 0.85, 0.88} |
| M1 | Spectral clustering on cosine affinity; choose K via **eigengap** with a wide cap (e.g. K≤20), **no** 2–4 prior |
| M2 | Hybrid: run M0 → take speaker-change boundaries → second look with spectral (local neighborhood or full re-cluster seeded by changes) |
| M3 | Optional: anchor windows → cluster → assign remaining windows |

Reuse embeddings across methods per clip (encode once per wav).

## Timing protocol

1. Process `timing_5min.wav` **twice** in one process after a fresh embedder
   load: record `model_load_sec` once, then `embed_sec`/`cluster_sec`/`n_windows`
   for pass1 and pass2 (warm).
2. Also time `concat_01_02_03.wav` (180 s) embed once.
3. Pin 2 threads if easy (`OMP_NUM_THREADS=2`, onnx threads 2). Note host CPUs.
4. Explain whether threshold changes affect wall (they should barely, if embed dominates).

## Quality outputs

For clip01–03, apartments, ninth, and concat (with offsets 0/60/120 for 01/02/03):
n_id, speech_sec per id, top1 share, timelines JSON. No invented names.

## Inputs

See `cloud_in/inputs/CLIP_INDEX.md`.

## Stop-list

No `eval/`, no gold, no crumb-primary, no K∈[2,4] mandate, no second embedder,
no ASR/LLM, no prod PR.

## Report

`cloud_out/report.md` with tables M0/M1/M2 (+M3 if run), timing cold/warm,
verdict: does spectral/hybrid recover the short solo cluster better than AHC?
Recommendation for local HUMAN_GATE only.

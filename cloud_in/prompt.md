# Stage D5.diar-twopass — cheap VAD draft + WeSpeaker fine

Research cloud agent. Read `cloud_in/agent/AGENTS.md`. Unattended. No PR.
No production pipeline edits (scratch under `cloud_out/scratch/` only).

## Why

Sliding WeSpeaker windows with overlap dominate wall time and can mix speakers at
boundaries. Test a **two-stage** approach: draft structure from VAD (+ cheap or
1-embed decisions), then a fine WeSpeaker pass with/without overlap.

## Shared preprocess (all stage-1 methods)

1. Silero VAD → regions → islands (`vad_premerge_gap_sec` as in demo config ~0.5 s).
2. Build `units` from islands with **&lt; 1.0 s glue**:
   - island &lt; 1 s with a previous unit → append to previous;
   - run of several &lt; 1 s → merge into one unit;
   - leading &lt; 1 s → merge into next.
3. Report `n_islands`, `n_units`, durations histogram.

## Stage 1 — draft

| id | What |
|---|---|
| **1A** | One **WeSpeaker** embedding per `unit`. Adjacent merge/keep by **cosine** (tune a simple threshold; report sensitivity lightly, e.g. 2–3 values). |
| **1B** | Adjacent merge/keep by **cheap spectral/MFCC/flux** distance — **no WeSpeaker**. |
| **1C** | Cheap features on units; allow **splitting** long units (change-point / spectral clustering on cheap affinity). May cut finer than VAD. |

Do not call stage-1B/1C “spectral” if you mean WeSpeaker spectral clustering — say **cheap-feature** explicitly.

## Stage 2 — fine (WeSpeaker)

Start from production-like islands (or report if you chain from stage-1 units).

| id | What |
|---|---|
| **2A** | Current demo: `window_sec=1.5`, `step_sec=0.75` (overlap) → AHC `distance_threshold=0.85` |
| **2B** | **No overlap**: `window_sec=step_sec=1.5` inside islands → AHC 0.85 |
| **2C** | **One WeSpeaker embed per glued unit** (no sliding window) → AHC 0.85 (optional: also spectral clustering on these vectors) |

## Timing (required)

On `timing_5min.wav` (and note short clips):

- `model_load_sec` (once)
- per method: `n_embed_calls`, `embed_sec`, `cluster_sec`, `n_windows` or `n_units`
- pin 2 threads when easy

Hypothesis: 2C ≪ 2A on `n_embed_calls`; 2B fewer calls than 2A but more than 2C.

## Quality outputs

Timelines + speech per id for clip01–03, apartments, ninth (and concat if cheap).
Soft focus (not gold):

- clip01 ~42–45 s short greeting — does any method isolate it cleanly?
- ninth short secondary — survive or glue?

No invented speaker names. Local humans score against private gold after ingest.

## Inputs

`cloud_in/inputs/CLIP_INDEX.md`

## Stop-list

No `eval/`, no gold, no crumb-primary, no K∈[2,4] mandate, no second DNN,
no ASR/LLM, no prod PR, no 3.0/1.5 window “speed” redo.

## Report

`cloud_out/report.md` with stage-1 and stage-2 tables, timing, verdict:
keep overlap? is cheap 1B/1C useful? is 2C enough for demo quality?

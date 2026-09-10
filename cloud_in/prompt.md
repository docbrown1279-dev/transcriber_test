# Stage D5.TTFT-diar — WeSpeaker speed + speaker split (research)

You are a **research** cloud agent. Read `cloud_in/agent/AGENTS.md` first.
Unattended run. Do **not** write production pipeline code. Do **not** open a PR.

## Why

Demo packing C needs diarization before TOC. On 2 vCPU, embed windows dominate
wall time. Separately, male speakers glue into one fat cluster (`SPEAKER_00`) while
crumbs appear as extra ids. Goal of this pack: **measure** window coarsening and
cluster-threshold / crumb heuristics on short clips. Local humans score purity
against private gold after ingest.

Out of scope here: H0 model warmup, file split+anchor (S2 product), Jina, ASR.

## Task

1. Use existing WeSpeaker path in the repo (`src/transcriber/diarization/…`,
   `config/base.yaml` embed settings). Prefer a small runner script under
   `cloud_out/scratch/` or `scripts/` that loads wav → VAD if required → diarize
   → prints cluster stats. Do not refactor the product pipeline.
2. **S1 — window presets** (on all packed clips):

   | preset | window_sec | step_sec |
   |---|---|---|
   | baseline | 1.5 | 0.75 |
   | A | 2.0 | 1.0 |
   | B | 3.0 | 1.5 |

   Record: `n_windows`, embed wall, cluster wall, speaker id count, speech_sec
   per id, top1 speech share, ids with speech &lt; 3 s (crumbs).

3. **Cluster tuner** (baseline window, or best S1 if clearly faster and not worse
   on soft criteria): `cluster_distance_threshold` ∈ `{0.80, 0.82, 0.85, 0.88}`.
   Same metrics. If linkage distances are available, note largest merge gap
   (“knee”) qualitatively.

4. **Crumb merge prototype** (post-cluster, offline): merge any speaker whose
   total speech ≤ 2.5 s into nearest centroid (cosine) or nearest large neighbor
   by time. Report before/after id counts. Do not require production merge.py.

5. Soft expectations (not gold — for your judgement section only):

   **Global bar:** for every packed clip, a **healthy** result is about **2–4**
   speaker ids with non-trivial speech (≳3–5 s each).  
   - **1** fat id ≈ undersplit (FAIL soft)  
   - **≥10** / many crumbs ≈ oversplit (FAIL soft)  
   Crumbs with speech ≲2.5 s should not count toward the 2–4 band (merge or ignore).

   | clip | soft expect |
   |---|---|
   | clip01, clip02 | 2–4 ids; ≥2 substantial male clusters (not one monologue) |
   | clip03 | 2–4 ids; woman-like cluster separate from ≥1 male |
   | test_apartments, test_ninth | ~3 speakers inside the 2–4 band |

6. Write `cloud_out/report.md` (tables + recommended preset/threshold or
   “WeSpeaker ceiling”), `cloud_out/results.json`, `cloud_out/run_meta.json`.
   Optional timelines for local review.

## Inputs

| Path | What |
|---|---|
| `cloud_in/inputs/CLIP_INDEX.md` | clip list |
| `cloud_in/inputs/clips/*.wav` | 3×60 s meeting slices |
| `cloud_in/inputs/regression/*.wav` | apartments + ninth soft regression |

Repo code/config already on the branch may be used read-only for calling diarize.

## Approved dependencies

Only what the project already uses for WeSpeaker / VAD (`uv sync`). Do not add
new packages unless BLOCKED without them (document in report).

## Stop-list

No `eval/`, no gold invention, no ASR, no LLM, no H0, no Jina/pyannote, no
production feature PRs, no force-push `main`.

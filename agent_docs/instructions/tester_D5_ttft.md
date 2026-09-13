# Tester instructions — D5.TTFT split (product, **local**)

Status precondition: `agent_docs/progress/stage_D5_ttft.md` contains `READY_FOR_TEST` (after Coder).  
Phase 0 (reference_full15) **may start now**, in parallel with Coder.

Plan: [`../plans/draft_ttft_split_product.md`](../plans/draft_ttft_split_product.md).  
Contract: [`../contracts/ttft_split.md`](../contracts/ttft_split.md) (G5.T1–T3).  
Coder: [`coder_D5_ttft.md`](coder_D5_ttft.md).  
Gates: G5.4 plus G5.T* in [`../contracts/quality_gates.md`](../contracts/quality_gates.md).

**Local only.** No cloud handoff. No GitHub Actions.  
Write scope: `tests/` + reports under `agent_docs/reports/d5_ttft_split/`.  
Do **not** edit `src/` to greenwash — file bugs for @Coder.  
Do **not** commit `eval/` (gitignore). Never commit secrets.

## Goal

Prove the demo path publishes a usable TOC in **≤ 300 s** on **2 CPU / 8 GiB**, then finishes without OOM, with EOS speakers still in the same ballpark as a full-file run.

## Phase 0 — eval reference (can start now)

**Not** `eval/d5_diar/gold`. Reference = full15 artifacts sliced by the same pause cuts.

1. Source (prefer existing, else re-run full 15′ with unified gain):  
   `cloud_out/artifacts/full15/{turns,transcript,chapters}.json`  
   and `cloud_in/inputs/artifacts/cut_plan_15min_3.json` (part01 end ≈ 291.4 s).
2. Slice those artifacts into part windows; write gitignored:

```
eval/d5_ttft_split/reference_full15/
  README.md                  # source job/commit; “not manual gold”
  full_{transcript,chapters,turns}.json
  part01_{transcript,chapters,turns}.json
  part02_*.json
  part03_*.json
```

3. Glue script: `scripts/check_ttft_part_glue.py` (extend if EOS compare needs a sibling script). Document the command in the README.

**Gate Phase 0:** files on disk + command documented. Missing full15 → note in report and skip EOS-vs-full checks (G5.T6 WARN), do **not** invent gold.

## Phase 1 — unit / contract (after READY_FOR_TEST)

Add tests that run on a **bare checkout** (no audio, no models) plus `requires_inputs` where packed clips exist.

| ID | Check |
|---|---|
| `[D5T-CFG-01]` | `ttft_split: false` still plans/runs the old step graph (no cut_plan required) |
| `[D5T-CFG-02]` | demo overlay has `ttft_split: true`; `file_max_db` present; no literals for cut bounds in src |
| `[D5T-CUT-01]` | pause-cut: long pause near ideal is chosen; no-pause window → midpoint; parts in `[min,max]` |
| `[D5T-GAIN-01]` | file path uses `file_max_db` (2.0); per-turn path still allowed 18 dB |
| `[D5T-DIAR-01]` | gallery assign: dist ≤ 0.85 → existing id; else new id; **not** whole-cluster H1 |
| `[D5T-DIAR-02]` | absorb < 1 s still applied after assign |
| `[D5T-EOS-01]` | remap keeps published ids when overlap is unique; does not require wav |
| `[D5T-UI-01]` | TestClient: speaker alias POST + segment speaker change **rejected** while `speakers_finalized=false` |
| `[D5T-UI-02]` | events JSON has `early_ready`; progress would redirect (payload test is enough; no Playwright) |
| `[D5T-REG-01]` | `uv run pytest tests/ -v` green; `ruff`/`mypy`/`bandit` on Coder’s paths |

Do not skip or xfail a failing test to get green.

## Phase 2 — G5.T hardware (15 min, cgroup)

Audio: `var/bench/d5/voice_002_15min.m4a` (already used for D5). Warm HF/WeSpeaker/GigaAM cache.

| ID | Check | Maps to |
|---|---|---|
| `[D5T-G5-01]` | Job with `ttft_split` completes under `--cpus=2 --memory=8g`; **no OOMKill** | G5.T2 |
| `[D5T-G5-02]` | `ttft_first_chapter_sec` ≤ **300** (job start → first valid `chapters.json`) | G5.T1 |
| `[D5T-G5-03]` | Peak RSS **< 7 GiB** | G5.4 |
| `[D5T-G5-04]` | `cut_plan.json` part1 `duration_sec` ≤ 300 | contract §1 |
| `[D5T-G5-05]` | Titles did not gate TTFT (first chapters write before or without titles) | plan |
| `[D5T-G5-06]` | Control: `ttft_split: false` still completes (may be the existing G5 number; no need to re-run if Coder smoke is documented) | G5.T3 |

Adapt Coder’s bench flag, e.g.:

```bash
docker run --rm \
  --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v "$HOST_SECRETS:/run/secrets/transcriber.env:ro" \
  -v "$PWD/var/bench/d5:/bench:ro" \
  -v "$PWD/agent_docs/reports/d5_ttft_split:/out" \
  -v transcriber-hf-cache:/home/app/.cache \
  -v transcriber-var:/var/transcriber \
  transcriber:runtime \
  python /app/scripts/bench_d5.py \
    --audio /bench/voice_002_15min.m4a \
    --mode b \
    --out /out/g5_ttft_15min.json
```

Record host, image digest/tag, cold vs warm, exact `ttft_first_chapter_sec`.

If TTFT is 300–360 s → **FAIL** (do not move the threshold). File a Coder bug: part1 too long, titles blocked publish, or extra embed/VAD.  
If part1 media > 300 s → FAIL the cut planner, not the clock.

## Phase 3 — quality vs reference_full15

On the same 15′ job after EOS:

| ID | Check |
|---|---|
| `[D5T-Q-01]` | Large speakers (speech ≳ 30 s) **≥ 3** on the full 15′ after EOS (not collapsed to 2) |
| `[D5T-Q-02]` | Glue / LCS coverage vs `reference_full15` part windows — use the documented script; WARN on packing differences, FAIL on dropped half of the text |
| `[D5T-Q-03]` | Hotspot abs **[365.0, 375.5]** after EOS: dump turns; human listen optional (`HUMAN_GATE`) |
| `[D5T-Q-04]` | Mid-run may flicker; do **not** require 5 ids matching full before EOS |

## Report layout

```
agent_docs/reports/d5_ttft_split/
  product_gate.md            # PASS / PASS_WITH_WARNINGS / FAIL + tables
  g5_ttft_15min.md
  g5_ttft_15min.json         # must include ttft_first_chapter_sec
  glue_vs_full15.md          # Phase 3
```

`product_gate.md` structure: verdict, G5.T checks, agent judgement (was the first TOC usable without waiting for the full file?), environment, deviations.

## Gate verdict

- **PASS:** G5.T1–T2, peak RSS, speaker lock tests, large-speaker count ≥ 3 after EOS.
- **PASS_WITH_WARNINGS:** TTFT ≤ 300 s but glue/hotspot messy; or titles empty on first TOC.
- **FAIL:** TTFT > 300 s, OOM, RSS ≥ 7 GiB, EOS collapse to 2 large speakers, `ttft_split: false` broken, speaker edits possible before EOS.

Append to `agent_docs/progress/stage_D5_ttft.md` and one line to `agent_docs/progress/log.md`.

## Out of scope

H1/V2 bakeoffs, Playwright, raising `file_max_db`, committing eval artifacts, claiming semantic quality vs manual diar gold.

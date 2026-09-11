# Stage D5.TTFT-split — part1 pause-cut + early chapters (no LLM)

You are the **research spike** cloud agent for TTFT file-split (S2). Read
`cloud_in/agent/AGENTS.md` and `cloud_in/agent/rules.md`, then this prompt.
**This stage overrides product defaults:** do **not** modify `src/`, `config/`,
`tests/`, or open a PR. Install nothing beyond what the existing `uv.lock` already
provides. Run unattended; finish with artifacts + timing under `cloud_out/` and
push this branch.

## Why

Full 15′ demo wall on 2 vCPU is ~10–12 min. Goal: first usable chapter ~5–6 min by
cutting the file at long pauses and running diarize+ASR+packing **only on part1**.
Centroid-anchor for part2 is **out of scope** here.

## Task (exact order)

1. Preflight: packed inputs exist; record host inventory in `cloud_out/run_meta.json`
   (`nproc`, `free -h`, `df -h .`, `ffmpeg -version`, `python3 --version`, git rev).
2. Read `cloud_in/inputs/artifacts/cut_plan_15min_3.json` — **do not invent new cuts**.
3. Split `cloud_in/inputs/audio/voice_002_15min.m4a` with ffmpeg (`-c copy` OK) into
   `cloud_out/artifacts/parts/part01.m4a` … `part03.m4a` using the plan's
   `start`/`end` (duration = end−start). Write `cloud_out/artifacts/parts/manifest.json`
   listing paths + durations (ffprobe).
4. Run **only part01** through the existing pipeline **without LLM titles**:

```bash
export HF_HUB_OFFLINE=1
uv run python scripts/run_ttft_part1.py \
  --audio cloud_out/artifacts/parts/part01.m4a \
  --job-dir cloud_out/artifacts/part01_job \
  --profile demo \
  --onnx-threads 2 \
  --out-timing cloud_out/artifacts/part01_timing.json
```

   If the helper script is missing, equivalent: load config, force
   `pipeline.toc_mode="a"`, `run_job(..., until="chunk")`, and write the same timing
   fields yourself. **Do not** call Gemini/NVIDIA/Qwen.

5. Copy/move key job artifacts to `cloud_out/artifacts/part01/`:
   `turns.json`, `transcript.json`, `chapters.json`, `speech.json`, `audio.json`
   (plus `part01_timing.json`).
6. Write `cloud_out/gate_ttft_part1.md` with:
   - part durations vs plan (tolerance ±1.0 s)
   - `speaker_count`, `n_turns`, `n_chapters`
   - `ttft_first_chapter_sec` and `ttft_plus_llm_budget_sec` (= TTFT + 2.0)
   - PASS hint if TTFT+2 ≤ 360 s on a 2-CPU-like host; otherwise record FAIL/WARN with
     host `nproc` (do not fake a 2-CPU machine)
7. Commit + **push branch** `cursor/d5-ttft-split`. Do **not** open a PR.

## Inputs

| Path | What |
|---|---|
| `cloud_in/inputs/audio/voice_002_15min.m4a` | 15′ slice of voice 002 |
| `cloud_in/inputs/artifacts/cut_plan_15min_3.json` | pause-balanced 3 parts |
| `cloud_in/inputs/artifacts/cut_plan_15min_3.md` | human summary |
| `cloud_in/inputs/STACK.md` | frozen stack |
| `scripts/run_ttft_part1.py` | runner (on this branch) |
| `scripts/plan_pause_cuts.py` | reference only |

## Diarization rules (must)

- `cluster_distance_threshold=0.85` (base/demo default)
- **Do not** drop short clusters / short turns beyond existing merge absorb in config
- Keep all speaker ids returned by AHC

## Stop-list

- No edits under `src/`, `config/`, `tests/`, `docs/`, `eval/`, `.env`
- No gold labels; do not read `eval/`
- No full-file ASR of all three parts (part01 only)
- No LLM titles / insights / report
- No force-push; no PR

## Deliverables

1. `cloud_out/artifacts/parts/{part01,part02,part03}.m4a` + `manifest.json`
2. `cloud_out/artifacts/part01/{turns,transcript,chapters,speech,audio}.json`
3. `cloud_out/artifacts/part01_timing.json`
4. `cloud_out/run_meta.json`
5. `cloud_out/gate_ttft_part1.md`
6. Branch push

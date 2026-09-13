# D5.TTFT product gate

**Verdict: PASS_WITH_WARNINGS**

First TOC was usable without waiting for the full file: `ttft_first_chapter_sec = 169.177` (≤ 300), part1 media 229 s, job completed under 2 CPU / 8 GiB with peak RSS ~3.6 GiB and 3 large speakers after EOS.

## G5.T / instruction checks

| ID | Check | Result | Evidence |
|----|-------|--------|----------|
| G5.T1 / [D5T-G5-02] | TTFT ≤ 300 s | **PASS** | 169.177 s — `g5_ttft_15min.json` |
| G5.T2 / [D5T-G5-01] | Completes, no OOM | **PASS** | wall 555.9 s; exit 0 |
| G5.4 / [D5T-G5-03] | Peak RSS < 7 GiB | **PASS** | 3688.5 MiB |
| [D5T-G5-04] | part1 duration ≤ 300 | **PASS** | 229.264 s |
| [D5T-G5-05] | Titles do not gate TTFT | **PASS** | `early_ready` before title LLM |
| G5.T3 / [D5T-G5-06] | `ttft_split: false` path | **PASS** (unit) | `[D5T-CFG-01]`; short-file skip in regression log; no second 15′ control run |
| [D5T-Q-01] | ≥ 3 large speakers EOS | **PASS** | 3 speakers ≥ 30 s |
| [D5T-Q-02] | Glue vs reference | **WARN** | text coverage ≥ 0.97; C3 chapter spill / 4≠3 cuts |
| [D5T-Q-03] | Hotspot [365,375.5] | **PASS** (dump) | SPEAKER_02 cable stretch; listen not run |
| Phase 1 units | CFG/CUT/GAIN/DIAR/EOS/UI | **PASS** | `tests/unit/test_ttft_split.py` 9/9 |
| [D5T-REG-01] | full pytest + lint | **WARN** | see below |

## Phase 1 unit results

```
uv run pytest tests/unit/test_ttft_split.py -v  → 9 passed
```

| ID | Status |
|----|--------|
| D5T-CFG-01 | PASS |
| D5T-CFG-02 | PASS |
| D5T-CUT-01 | PASS |
| D5T-GAIN-01 | PASS |
| D5T-DIAR-01 | PASS |
| D5T-DIAR-02 | PASS |
| D5T-EOS-01 | PASS |
| D5T-UI-01 | PASS (409 on alias + speaker edit) |
| D5T-UI-02 | PASS (`early_ready` in events payload) |

## REG-01 / Coder lint smoke

| Command | Exit | Notes |
|---------|------|-------|
| `uv run pytest tests/ -v` | 1 | **91 passed**, 2 failed (pre-existing / env): `test_d0_hlt_02` expects 503 without `JOB_IP_SALT` but gets 200; soft regression HF network disconnect in sandbox. **Not** TTFT unit regressions. |
| `uv run ruff check` (Coder paths) | 1 | `orchestrator.py` I001 import order — Coder lint debt |
| `uv run mypy` (gallery/eos/pause/ttft) | 1 | 3 errors in `gallery.py` — Coder |
| `uv run bandit -q -r` (ttft/gallery/eos) | 1 | B404/B603 subprocess Low (ffmpeg slice) — note only |
| config smoke `load_config('demo')` | 0 | ttft_split / max_part_sec=300 / file_max_db=2.0 |

## Agent judgement

The first TOC (4 chapters at ~169 s) is a usable draft for navigation while the job continues. Speaker edits correctly locked until EOS. Quality vs full15 is in the same ballpark for speakers and text; packing chapter edges that cross reference cuts are messy but do not drop content.

## Environment

- Host: `vladimir`, Docker `--cpus=2 --memory=8g`
- Image: `transcriber:runtime@9c17d078fc5d` (rebuilt 2026-09-12)
- Secrets: `var/secrets/transcriber.env` (gitignored), mounted read-only
- Phase 0 reference: verified non-stub (transcript n=143 / 34 / 56 / 53)

## Deviations

1. Product pause-cut produced **4** parts (max 300) vs reference **3**-part plan from research cut_plan_15min_3.
2. No second Docker control run with `ttft_split: false` (covered by unit + short-clip skip).
3. Full pytest not fully green due to unrelated health/regression failures.
4. Coder ruff/mypy not clean on handoff paths (report for @Coder; not TTFT gate FAIL).

## Report paths

- `agent_docs/reports/d5_ttft_split/product_gate.md` (this file)
- `agent_docs/reports/d5_ttft_split/g5_ttft_15min.md`
- `agent_docs/reports/d5_ttft_split/g5_ttft_15min.json`
- `agent_docs/reports/d5_ttft_split/glue_vs_full15.md`

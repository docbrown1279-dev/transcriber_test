# HANDOFF — stage D5.TTFT-split (part1)

| Field | Value |
|---|---|
| CURRENT stage | **D5.TTFT-split — pause cut + part1 diar/ASR/chunk (no LLM)** |
| Branch | `cursor/d5-ttft-split` |
| Contract | read **`cloud_in/`** + `scripts/run_ttft_part1.py`; write **only** `cloud_out/`; **do not** change `src/` / `config/` / `tests/` |
| Role | `cloud_in/agent/AGENTS.md` + `rules.md` — **prompt overrides**: research spike, no product code |
| Task | `cloud_in/prompt.md` |
| Secrets | none for this stage (`HF_HUB_OFFLINE=1`; weights already local) |
| Deliverables | parts + part01 artifacts + timing + `gate_ttft_part1.md` + **push branch** (no PR) |

## Order of work

1. Preflight pack + host inventory → `cloud_out/run_meta.json`
2. ffmpeg-split 15′ audio by packed cut plan → `cloud_out/artifacts/parts/`
3. `scripts/run_ttft_part1.py` on **part01 only** (`onnx_threads=2`, toc_mode a, until chunk)
4. Gate markdown + push `cursor/d5-ttft-split`

## Forbidden

`eval/`, `.env`, `data/` (use packed audio only), `docs/` writes, `src/` edits, LLM API calls,
force-push, opening a PR.

## After the cloud run (local operator only — cloud must ignore this)

Do **not** read or create `eval/` in the cloud. Glue-check against prior windows is done
**locally after pull** by the human/orchestrator (baselines stay gitignored on the laptop).

Cloud deliverable for comparison: `cloud_out/artifacts/part01/{transcript,chapters}.json`
plus timing/gate.
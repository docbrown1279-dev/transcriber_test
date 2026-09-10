# HANDOFF — D5.TTFT diar research

| Field | Value |
|---|---|
| CURRENT stage | **D5.TTFT-diar** — WeSpeaker windows + cluster tuner (research only) |
| Branch | `cursor/d5-ttft-diar` |
| Contract | read **`cloud_in/`** only → write **`cloud_out/`** (+ optional throwaway `scripts/` helper). No product `coder_*.md`. |
| Role | `cloud_in/agent/AGENTS.md` + `cloud_in/agent/rules.md` |
| Task | `cloud_in/prompt.md` |
| Secrets | `HF_TOKEN` if Hub download needed for WeSpeaker weights; no Gemini |
| Deliverables | `cloud_out/report.md`, `results.json`, `run_meta.json`, push branch (no PR) |

## Order of work

1. Preflight: role files, prompt, packed wavs (`CLIP_INDEX.md`)
2. Host inventory → `run_meta.json`
3. Run S1 window A/B + cluster threshold grid on packed clips (diarize only)
4. Optional crumb-merge prototype on cluster stats (long-file rule can be simulated with speech_sec threshold)
5. Write reports → commit → **push this branch**. Do **not** open a PR.

## Forbidden

`eval/` (gold), H0 warmup, ASR, LLM, Jina, pyannote, production pipeline/UI/contracts,
force-push, opening a PR, inventing gold labels.

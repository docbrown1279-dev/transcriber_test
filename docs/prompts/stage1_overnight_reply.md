# Prompt — reply to waiting agent (overnight)

If the agent already paused for Phase A approval, paste this:

---

**approve Phase A — full unattended green light for the entire Stage 1.**

Do not ask for further package approvals. Install what you need from `docs/environment.md` (and sensible extras for denoise/LLM as you go), create `.venv`, download models, and run ASR → denoise → chunking → LLM → reports without pausing for confirmations.

Constraints still apply: Whisper-family only; denoise as separate A/B; **hard budgets** (ASR ≤3, denoise ≤3 methods, chunking ≤2, local LLM ≤1, Gemini ≤3 + NVIDIA ≤3 API calls total); no infinite retries; local first; never log secrets; reports in Russian.

When done (or hard-blocked), commit and push results to your branch / PR: `results/reports/research_report.json`, `notes.md`, scripts, artifacts. Do not wait for me — I’m offline until morning.

Proceed now.

---

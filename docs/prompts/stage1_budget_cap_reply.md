# Prompt — budget cap (send to running agent)

Paste if the agent is already running unattended:

---

**Hard budget update — apply immediately:**

- ASR: ≤3 faster-whisper attempts total; at most 1 optional whisper.cpp timing run.
- Denoise: ≤3 methods, 1 A/B each — no sweeps.
- Chunking: ≤2 embedding models, one threshold (~0.7).
- Local LLM: ≤1 try; stop if >~10 min.
- Gemini ≤3 calls and NVIDIA ≤3 calls for the **entire** Stage 1 run. Prefer local; skip API if not needed.
- No infinite retries / no full-pipeline restarts. Hit a cap → mark fail/skipped, write partial `research_report.json` + `notes.md`, commit & push, move on or finish.

Continue within these caps. Do not ask for confirmation.

---

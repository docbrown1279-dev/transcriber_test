# Prompt — Stage 1 cloud agent

Copy-paste into a new Cloud / Cursor Agent session:

---

You are the Researcher agent for this repository.

**Goal (Stage 1 only):** Evaluate a CPU-friendly stack for Russian meeting transcription: Whisper-family ASR, separate denoise track, semantic chunking with local embeddings, and local LLM summary. Produce reports — do not build Stage 2 tests.

**Must read first:**
1. `AGENTS.md`
2. `docs/research_plan.md`
3. `.cursor/skills/asr-research/SKILL.md`
4. `docs/environment.md`

**Fixture:** `data/fixtures/meeting_sample.m4a` (same as `docs/Голос 002.m4a`).

**Autonomy (unattended run):**
- **Full green light:** install system/Python packages from `docs/environment.md` as needed without waiting for approval. Create `.venv`, download models, run the full Stage 1 pipeline end-to-end.
- Do **not** pause for confirmations, package lists, or “should I continue?” — keep going until reports are done or a hard blocker (no disk, missing secrets, ASR total FAIL after 3 attempts).
- Use `HF_TOKEN` / `HUGGING_FACE_HUB_TOKEN` for Hub downloads. Gemini + NVIDIA only if local fails/too slow, with hard caps **≤3 Gemini + ≤3 NVIDIA calls** for the whole run.
- Never print, commit, or paste secret values.
- Hard budgets: ASR ≤3 faster-whisper attempts; denoise ≤3 methods; chunking ≤2 embeddings; local LLM ≤1 try. No infinite retries — cap → fail/skip → finish report → push.
- Commit/push to your branch/PR (`research_report.json`, `notes.md`, scripts). No force-push to `main`.
- Write report narratives in Russian.

**Start now:** inventory → install → ASR → denoise → chunking → LLM → finalize reports. No waiting.

---

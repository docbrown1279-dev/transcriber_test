---
name: cloud-agent-setup
description: >-
  Cursor Cloud RESEARCH only — prepare Cloud Agent infra before a research
  handoff (source control, environment, secrets, spend). Use for staged
  research cloud_in packs, not for general product planning.
---

# Cloud Agent setup (Cursor Cloud research)

**Scope:** инфраструктура Cloud Agent для **исследовательских** handoff. Не скилл общего planner.

Run **before** packing `cloud_in/` on the first handoff of a project, or when the cloud VM/env changed. Do **not** pack stage prompts here.

## Docs (verify current)

- Overview: https://cursor.com/docs/cloud-agent
- Setup / environment: https://cursor.com/docs/cloud-agent/setup
- Security / secrets: https://cursor.com/docs/cloud-agent/security-network

If instructions diverge from this skill, **prefer the live docs** and note the delta in `progress/log.md`.

## Checklist

1. **Source control** — GitHub/GitLab/Bitbucket/Azure DevOps connected for the Cursor account; repo has read-write so the agent can push the handoff branch.
2. **Team access** — Cloud agents for this team can open the repository (Integrations + repo permissions).
3. **Environment** — Snapshot, Dockerfile, or `.cursor/environment.json` so the agent can install deps and run `scripts/` (same class of setup as a human laptop). See setup docs.
4. **Secrets** — API keys only via Cloud Agents dashboard / Secrets — never commit `.env`. Restart cloud agent after adding secrets if needed.
5. **Spend / model** — limit and model/context size chosen for this run.
6. **Hooks (optional)** — `.cursor/hooks.json` in repo if format/check should run in the cloud VM (user-level `~/.cursor/hooks.json` is **not** available in cloud).

## Output

Append one line to `progress/log.md`, e.g. `cloud infra check ok` or `cloud infra: fix {item}`.

Then continue with the **cloud-handoff** rule (pack `cloud_in/`, push branch).

---
description: Pull cloud_out reports first; checkout full stage code only if gate PASS
---

# cloud_pull

You are the **local operator agent**. Run the two-phase pull **immediately**. Do **not** ask the user for confirmation.

## Do now

1. Run with full permissions (git write + network):

```bash
./scripts/cloud_pull.sh
```

Use Shell `required_permissions: ["all"]`. Do not pass `--force-code` unless the user explicitly asked to take FAIL/BLOCKED code anyway. Do not pass `--reports-only` unless they only want reports.

2. Interpret the script exit / `RESULT:` line and reply in Russian:

| RESULT | What to tell the user |
|---|---|
| `OK (reports + code)` | Отчёты в `agent_docs/reports/D*/`, ветка с кодом checkout'нута. Предложить `./scripts/cloud_pr.sh` (или запустить его сразу, без лишних вопросов, если пользователь ждёт PR). |
| `NO_REPORTS` | Агент ещё не запушил `cloud_out/` — подождать и повторить `/cloud_pull`. |
| `FAIL` / `BLOCKED` / `UNKNOWN` | Показать путь к gate/BLOCKED. Код **не** скачан — так задумано. Не делать merge. |

3. If the script ended with OK and the user did not say “без PR”, run:

```bash
./scripts/cloud_pr.sh
```

and paste the draft PR URL.

4. Do not weaken gates. Do not edit `src/` to “fix” a FAIL. Do not read `.env` or `eval/`.

## Why two phases

- Phase 1 always materializes `cloud_out/` reports into `agent_docs/reports/{stage}/`.
- Phase 2 checks out the full handoff branch (application code) **only** when the gate verdict is `PASS` or `PASS_WITH_WARNINGS`.

Stage prompts differ (`cloud_in/prompt.md` per stage); the branch name also differs — both come from `cloud_in/HANDOFF.md`.

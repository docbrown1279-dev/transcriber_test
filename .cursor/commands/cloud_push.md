---
description: Pack check + commit/push cloud_in handoff; print Cloud Agent branch and paste prompt
---

# cloud_push

You are the **local operator agent**. Run the handoff **immediately**. Do **not** ask the user for confirmation to commit, push, create a branch, or proceed.

## Do now (in order)

1. Run with full permissions (git write + network):

```bash
./scripts/cloud_status.sh
```

2. If status is **FAIL** — stop. Reply in Russian with the exact missing paths from the script output. Do not invent files. Do not push.

3. If status is **OK** — run immediately:

```bash
./scripts/cloud_handoff.sh
```

Use Shell `required_permissions: ["all"]` (or git_write + full_network) so push is not blocked by sandbox. Do not use `--dry-run` unless the user asked for a dry run.

4. From the script output, show the user **clearly** in Russian:

- **Ветка для Cloud Agent:** the `Branch` / `cursor/…` line (this is where they must start the cloud run)
- **Этап:** stage id (D0, D1, …) — each stage has its **own** `cloud_in/prompt.md`; never reuse an old paste for a new stage
- **Промпт для вставки:** the full `=== PASTE INTO CLOUD AGENT ===` … `=== END ===` block from the script, unchanged
- **Файл полного ТЗ этапа:** `cloud_in/prompt.md`

5. Do not open a PR. Do not start inventing code. Do not read `.env` or `eval/`.

## Done when

- Either FAIL report with missing files, or successful push + paste block shown to the user.

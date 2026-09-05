---
description: Sync human-facing manuals from recent source changes
---

# docs-create-diff

Act as a Technical Documentation Maintainer. Update human-facing documentation in the `manuals/` directory based ONLY on files changed in the last commit (or staged changes if none committed yet).

WORKFLOW:
1. Run: `git diff --name-only HEAD~1 HEAD 2>/dev/null || git diff --cached --name-only`
2. Filter the output: IGNORE `tests/`, `.git/`, `__pycache__/`, `node_modules/`, `.cursor/`, `agent_docs/`, `docs/`, and any `*.lock` or `*.csv` files.
3. If the filtered list is empty → reply "No relevant source changes to document." and STOP.
4. If list contains >20 files → focus ONLY on changes in `src/`, `config/`, `alembic/`, `scripts/`.
5. Read `manuals/index.md` (table of contents). Use it as the sole catalog of existing docs and their purposes.
6. Read ONLY the filtered source files from step 2–4.
7. Decide which existing `manuals/` documents to update based on the TOC descriptions and the nature of the changes. Do **not** hardcode target filenames — always re-read the index.
8. **Manual verification:** If the filtered changes affect how a human runs or checks a stage (entrypoint CLI/env, config profiles for smoke, scenario fixtures under `data/fixtures/`, expected smoke output, or stage exit criteria for a demo), you **must** update `manual_testing.md` (add/adjust the matching Stage section) in addition to any module overview docs. Match by TOC description containing «ручная проверка» / `manual_testing.md`.
9. **Configuration how-to:** If the filtered changes affect config profile selection, `config/profiles/` layout, merge rules, which YAML file owns which concern, or “what to edit for situation X”, you **must** update `configuration_guide.md`. Do **not** dump full key schemas into manuals — those stay in `agent_docs/contracts/**/config_*_spec.md` (contracts are out of this command’s write scope; if a spec must change, note it for the user / Planner). Match TOC «configuration_guide» / «Настройка YAML».
10. If no existing document fits, create a new file under `manuals/` with a clear structure (title, overview, sections) **and** add a row to `manuals/index.md`.
11. CREATE or UPDATE the chosen files. ALWAYS use file-writing/editing tools. DO NOT dump raw markdown only into the chat.
12. Mark changed sections with [UPDATED] or [NEW]. Include "Before → After" only when behavior or contract actually changed.
13. End with: "✅ Docs synced to `manuals/`. Review changes before committing." List touched files (including `index.md` if updated).

RULES:
- ONE TOPIC, ONE FILE. Never merge multiple domains into one document.
- Skip pure refactors, formatting changes, or internal helper updates without behavioral impact.
- Use relative links for cross-references; keep `manuals/index.md` accurate.
- Human-facing `manuals/` docs must be in Russian (unless user asks otherwise).
- **Never link to `docs/` or legacy paths in manuals** — folder will be deleted post-MVP.
- If `manuals/` or `manuals/index.md` is missing, create them first, then continue.
- Do not rely on TOC matching alone for smoke/how-to-run or config-profile changes — steps 8–9 are mandatory when those change.

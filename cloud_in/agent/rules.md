# Cloud agent rules — coding, testing, reporting

Stable across stages. Read together with `AGENTS.md` and the current `prompt.md`.

## 1. Tooling (single source of truth)

| Purpose | Command |
|---|---|
| Sync environment | `uv sync` |
| Add dependency | `uv add <package>` (only packages listed as approved in `prompt.md`) |
| Tests | `uv run pytest tests/ -v` |
| Lint | `uv run ruff check src/` |
| Types | `uv run mypy src/` |
| Security | `uv run bandit -r src/ -ll` |

Forbidden: `pip install`, `poetry`, bare `python -m pip`, editing lockfiles by hand, adding a
package that the stage prompt did not approve.

## 2. Code norms

1. No magic numbers. Every threshold, limit, path and model name comes from `config/` or the
   environment. A literal in `src/` is a defect.
2. Explicit data flow: pass state through arguments, no global mutable state, no import-time side
   effects.
3. Fail fast and loudly. No bare `except:`, no `except: pass`, no swallowing a provider error into
   a default value. Errors name the offending component and input.
4. Layering: `web` → `pipeline` → area modules (`asr`, `vad`, …) → `models`. A lower layer never
   imports a higher one; pipeline code depends on protocols from `<area>/base.py`, never on a
   concrete engine class.
5. A component unavailable in the active profile raises `ComponentUnavailableError`; a component
   scheduled for a later stage raises `StageNotImplementedError`. Silently substituting another
   engine is forbidden.
6. Smallest correct diff. No drive-by refactors, no reformatting of untouched files.
7. Docstrings on public APIs in Russian; comments and identifiers in English.
8. Logs carry job ids, stage names, durations and sizes — never transcript text, never a raw
   client IP, never a secret.

## 3. Artifacts

1. Artifacts are the only contract between stages: validate on read **and** on write against the
   pydantic model.
2. A stage never rewrites an upstream artifact. Corrections are additive files
   (`suggestions.json`), not edits of `transcript.json`.
3. An empty ASR result is a valid value; a missing interval is a hole and is recorded as such.
4. Timecodes are copied, never recomputed by a model and never invented.
5. Deterministic serialization: sorted keys, 3-decimal floats, so diffs are reviewable.

## 4. Tests

1. Unit and contract tests must pass on a bare checkout: no audio, no models, no network.
2. Tests needing packed data use the `requires_inputs` marker and the `TRANSCRIBER_FIXTURES_DIR`
   fixture (default `cloud_in/inputs/`); they skip when the data is absent.
3. LLM tests run on recorded cassettes under `tests/fixtures/llm/`; live calls belong to the gate
   run only and count against the Gemini budget.
4. Assertions on model output check invariants (schema, timecode provenance, counts, absence of
   stamp phrases) — never exact generated wording.
5. Never skip, delete, weaken or `xfail` a failing test to get green. Report the defect instead.
6. Map every test to a `[TEST-ID]` from the stage instructions.

## 5. Gate reporting

`cloud_out/gate_D{N}.md` structure:

```
# Gate D{N} — <stage name>
## Verdict: PASS | PASS_WITH_WARNINGS | FAIL
## Checks
| id | check | value | threshold | status |
## Agent judgement
<the qualitative verdict the gate asks for, with concrete examples>
## Environment
<host, versions, wall time, peak RSS, LLM calls: provider + purpose>
## Deviations and blockers
<what was skipped or capped, and why>
```

Report what happened, including failures and skipped paths. A silent omission is worse than a
documented `FAIL`.

## 6. Stop conditions

Budget exhausted, required secret missing, required input missing, disk or memory exhausted, or
the gate still failing after two honest fix attempts. In every case: finish what is valid, write
`cloud_out/gate_D{N}.md` (or `BLOCKED.md`), commit, open the PR, stop.

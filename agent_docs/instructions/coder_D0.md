# Coder instructions — stage D0 (skeleton, ports, stubs)

Status precondition: `agent_docs/progress/stage_D0.md` contains `INSTRUCTIONS_READY`.
Contracts to follow: [`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md),
[`../contracts/module_interfaces.md`](../contracts/module_interfaces.md),
[`../contracts/config_profiles.md`](../contracts/config_profiles.md),
[`../contracts/quality_gates.md`](../contracts/quality_gates.md) (gate G0).

Goal: a runnable skeleton of the `demo` application — config profiles, artifact models, component
registry with stubs, pipeline stage graph, `/healthz`, CLI. **No model-backed stage is implemented
here.** Do not invent behaviour that is not in the contracts; if a contract is ambiguous, write
`cloud_out/BLOCKED.md` and stop.

## Scope

Write only these paths:

```
pyproject.toml
config/demo.yaml, config/dev.yaml, config/prod.yaml
src/transcriber/__init__.py
src/transcriber/errors.py
src/transcriber/registry.py
src/transcriber/cli.py
src/transcriber/config/{__init__.py,schema.py,loader.py}
src/transcriber/models/{__init__.py,artifacts.py,legacy.py}
src/transcriber/audio/{__init__.py,base.py}
src/transcriber/vad/{__init__.py,base.py}
src/transcriber/diarization/{__init__.py,base.py}
src/transcriber/asr/{__init__.py,base.py}
src/transcriber/correction/{__init__.py,base.py}
src/transcriber/chunking/{__init__.py,base.py}
src/transcriber/llm/{__init__.py,base.py,prompts/.gitkeep}
src/transcriber/insights/{__init__.py,base.py}
src/transcriber/export/{__init__.py,base.py}
src/transcriber/quality/{__init__.py,ru_ratio.py,checks.py}
src/transcriber/pipeline/{__init__.py,steps.py,orchestrator.py,artifacts.py,events.py}
src/transcriber/jobs/{__init__.py,store.py}
src/transcriber/web/{__init__.py,app.py,health.py}
```

Do not create `tests/` (owned by @Tester), do not touch `docs/`, `agent_docs/contracts/`,
`eval/`, `data/`, `.env`.

## Steps

1. **Preflight.** Verify the packed inputs listed in `cloud_in/prompt.md` exist. Missing input →
   `cloud_out/BLOCKED.md` with the exact missing names, stop.

2. **`pyproject.toml`.** Python `>=3.12`, build with `uv`, project name `transcriber`, package
   under `src/`. Runtime dependencies for D0 only (approved set):
   `fastapi`, `uvicorn[standard]`, `jinja2`, `python-multipart`, `pydantic>=2`,
   `pydantic-settings`, `pyyaml`, `numpy`, `typer`.
   Dev group: `pytest`, `pytest-asyncio`, `httpx`, `ruff`, `mypy`, `bandit`.
   Declare **empty placeholder** optional groups for later stages without installing them:
   `asr`, `diarize`, `embed`, `llm-local`. Configure `ruff`, `mypy` (strict on `src/`), `bandit`,
   and `pytest` markers `requires_inputs`, `requires_llm`, `slow`.

3. **`config/`.** Write the three profiles exactly as `config_profiles.md` §2–§4 describes; no
   extra keys, no renaming. Secrets appear only as `*_env` variable names.

4. **`config/schema.py` + `loader.py`.** Pydantic models with `extra="forbid"` for every config
   section; `load_config(profile: str | None)` resolves the profile from `APP_PROFILE` (default
   `demo`), reads the yaml, validates, and returns `AppConfig`. Unknown keys and out-of-range
   thresholds fail loudly with the offending key path. Never read `.env`; secrets come from
   `os.environ` by the name given in config.

5. **`models/artifacts.py`.** One pydantic model per artifact from `pipeline_artifacts.md` §1–§10
   with validators: `end > start`, times non-negative and monotonic within a list,
   `schema_version == "1"`, `source_ids` non-empty, `key_point.src` non-empty. Provide
   `load_artifact(path, model)` / `dump_artifact(artifact, path)` helpers with deterministic JSON
   (sorted keys, 3-decimal floats).

6. **`models/legacy.py`.** The packed research transcripts (`cloud_in/inputs/artifacts/baseline_*.json`)
   use the research shape: top-level `audio`, `model`, `provider`, `execution_mode`, `gain`,
   `runtime_sec`, and `segments[]` with integer `id` and no `turn_id` / `schema_version`.
   Implement `load_legacy_transcript(path) -> TranscriptArtifact`: map `id → f"s{id:04d}"`,
   `model/provider → engine`, keep `start`/`end`/`speaker`/`text` verbatim, set
   `empty = not text.strip()`, `holes = []` (the research file does not carry them), and take
   `max_segment_sec` from config. Never edit the packed file; conversion produces a new artifact.
   Expose it as `transcriber convert-legacy <src> <dest>`.

7. **`errors.py`.** `TranscriberError` base plus `ComponentUnavailableError(component, profile,
   hint)`, `UnknownComponentError(area, key)`, `StageNotImplementedError(stage)`,
   `ConfigError`, `PreflightError`. Every message names the offending item; no bare `except`.

8. **Ports.** In each `<area>/base.py` define the `Protocol` from `module_interfaces.md` §1 with
   Russian docstrings on public members. No implementations in D0.

9. **`registry.py`.** `register(area, key, factory, profiles)`, `build(area, key, profile)`,
   `available(area, profile)`. Register **every** key from `module_interfaces.md` §3. Since no
   engine exists yet, each factory raises either `ComponentUnavailableError` (key not allowed in
   the active profile) or `StageNotImplementedError` (allowed but arriving in a later stage) —
   pick by the profile table, never by silently substituting another component.

10. **Pipeline.** `steps.py` declares the ordered stage graph
   (`normalize, vad, diarize, asr, correction_suggest, chunk, titles, insights_extract, report`)
   with `stage`, `produces`, `requires` per `module_interfaces.md` §4. `orchestrator.py` resolves
   status per stage: `done` when `produces` exists and validates, `pending` when its component is
   registered for the profile, `unavailable` otherwise; running an unimplemented stage raises
   `StageNotImplementedError`. `events.py` holds `StageEvent`; `artifacts.py` resolves job paths.
   The orchestrator must never fabricate an artifact.

11. **`jobs/store.py`.** Create/read `job.json` per contract §10, append `StageEvent`s, hash the
    client IP with `JOB_IP_SALT`. TTL sweeping and the queue belong to D4 — leave them out, do not
    stub them silently.

12. **`quality/ru_ratio.py` + `checks.py`.** Implement `russian_word_ratio` exactly as
    `quality_gates.md` G1 defines (tokens `\w+` of length ≥ 2, lowercase, `ё → е`, all-Cyrillic
    counts as Russian, digits and punctuation excluded) plus a latin-character counter. `checks.py`
    exposes `CheckResult`/`CheckReport` used by later gates. Thresholds come from config, not
    literals.

13. **`web/{app.py,health.py}`.** FastAPI app with `GET /healthz` only. The startup self-check
    reports per component: config valid, registry keys available for the profile, storage root
    writable, `ffmpeg`/`ffprobe` present, required env vars set, and — when
    `cloud_in/inputs/audio/test_voice.m4a` exists — a successful ffprobe with duration in 80–90 s.
    200 when all pass, 503 with the failing component names otherwise. No upload route and no ASR
    in D0.

14. **`cli.py`.** Typer app with `plan --job <dir>` (prints stage graph with statuses, exit 0),
    `validate <path>…` (loads artifacts into models, exit non-zero on invalid),
    `convert-legacy <src> <dest>` (step 6), `probe-audio <path>` (ffprobe duration/size JSON, exit
    non-zero if unreadable), `healthcheck` (same self-check as `/healthz`, without serving).
    Entry point `transcriber` in `pyproject.toml`.

15. **Verify locally**, then hand off:

    ```
    uv sync
    uv run ruff check src/
    uv run mypy src/
    uv run bandit -r src/ -ll
    uv run transcriber probe-audio cloud_in/inputs/audio/test_voice.m4a
    uv run transcriber convert-legacy cloud_in/inputs/artifacts/baseline_transformers.json \
        var/jobs/fixture/transcript.json
    uv run transcriber plan --job var/jobs/fixture
    uv run transcriber validate var/jobs/fixture/transcript.json
    uv run transcriber healthcheck
    ```

16. **Report.** Write `cloud_out/gate_D0.md` (check ids G0.0–G0.7 with values and statuses) and
    `cloud_out/run_meta.json` (branch, commit, package versions, wall time). Append to
    `agent_docs/progress/stage_D0.md`:

    ```
    ## YYYY-MM-DD — Coder
    - STATUS: READY_FOR_TEST
    - Files: <paths>
    - Verified: <commands and exit codes>
    ```

    Commit and open a PR from branch `cursor/demo-d0-skeleton`.

## Acceptance criteria

- Every path in **Scope** exists; nothing outside it is modified.
- `ruff`, `mypy`, `bandit` exit 0; no rule disabled and no blanket `# noqa`.
- Registry contains every contract key; prod-only keys raise `ComponentUnavailableError` under
  `demo`, later-stage keys raise `StageNotImplementedError`, unknown keys raise
  `UnknownComponentError`.
- `transcriber plan` prints the nine stages in contract order with a status each and exits 0.
- `transcriber validate` accepts the packed fixture artifacts and rejects a deliberately corrupted
  copy (e.g. `end < start`) with a non-zero exit.
- No literal thresholds in `src/` — all from config; no fixture or placeholder data written into a
  production artifact path.
- `GET /healthz` behaves per step 12.

## Notes

Docstrings on public APIs in Russian; comments, identifiers and commit messages in English; user
summary in Russian. Dependencies only via `uv add` from the approved list above — any extra
package needs the user's approval first, recorded in `cloud_out/gate_D0.md`.

# Tester instructions — stage D0 (skeleton, ports, stubs)

Status precondition: `agent_docs/progress/stage_D0.md` contains `READY_FOR_TEST`.
Contracts: [`../contracts/module_interfaces.md`](../contracts/module_interfaces.md),
[`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md),
[`../contracts/config_profiles.md`](../contracts/config_profiles.md),
[`../contracts/quality_gates.md`](../contracts/quality_gates.md) (gate G0).

Write scope: `tests/` only. Never edit `src/`, `config/`, contracts, or `docs/`. A failing test is
a defect report for @Coder, never a reason to weaken an assertion.

## Test layout

```
tests/conftest.py
tests/unit/test_config_loader.py
tests/unit/test_registry.py
tests/unit/test_pipeline_plan.py
tests/unit/test_ru_ratio.py
tests/unit/test_jobs_store.py
tests/unit/test_health.py
tests/contract/test_artifact_models.py
tests/contract/test_packed_fixtures.py
tests/fixtures/artifacts/*.min.json
```

`conftest.py` provides: `tmp_job_dir`, `demo_config`, `dev_config`, `prod_config`, and
`fixtures_dir` resolving `TRANSCRIBER_FIXTURES_DIR` (default `cloud_in/inputs/`). Tests needing
packed data are marked `@pytest.mark.requires_inputs` and **skip** when the directory is absent —
unit and contract tests must pass on a bare checkout with no audio and no network.

## Test cases

| ID | File | What |
|---|---|---|
| `[D0-CFG-01]` | `test_config_loader.py` | `demo`, `dev`, `prod` load and validate; `APP_PROFILE` selects the profile; default is `demo` |
| `[D0-CFG-02]` | | unknown key in a config section fails with the key path in the message |
| `[D0-CFG-03]` | | demo values match the contract: `audio.max_minutes=15`, `asr.max_segment_seconds=25`, `chunking.similarity_threshold=0.70`, `limits.requests_per_ip_per_day=1`, `result_ttl_hours=24`, `llm.provider=gemini` |
| `[D0-CFG-04]` | | `dev` selects `local_llama`, `prod` selects local components; secrets appear only as env var names, never as values |
| `[D0-REG-01]` | `test_registry.py` | every area/key pair from `module_interfaces.md` §3 is registered |
| `[D0-REG-02]` | | prod-only keys (`pyannote31`, `late_chunking_jina`, `domain_dictionaries`, `pdf`, `openai_compat`) raise `ComponentUnavailableError` under `demo`, and the error names component, profile and hint |
| `[D0-REG-03]` | | keys allowed in `demo` but arriving later raise `StageNotImplementedError`, not a silent fallback to another component |
| `[D0-REG-04]` | | unknown key raises `UnknownComponentError`; `available("llm", "demo")` contains `gemini` and excludes `local_llama` |
| `[D0-PLN-01]` | `test_pipeline_plan.py` | stage graph order equals the contract order (nine stages) |
| `[D0-PLN-02]` | | a job seeded with a valid `transcript.json` reports `normalize…asr` as `done` and later stages as `pending`/`unavailable` |
| `[D0-PLN-03]` | | an invalid `produces` artifact is **not** counted as `done` |
| `[D0-PLN-04]` | | calling an unimplemented stage raises `StageNotImplementedError` and writes no artifact file |
| `[D0-ART-01]` | `test_artifact_models.py` | every example JSON from `pipeline_artifacts.md` §1–§10 round-trips through its model |
| `[D0-ART-02]` | | rejections: `end <= start`, negative time, non-monotonic segment list, missing/other `schema_version`, empty `source_ids`, `key_point` without `src` |
| `[D0-ART-03]` | | `dump_artifact` output is deterministic (same bytes on re-dump) and floats keep 3 decimals |
| `[D0-ART-04]` | | `report.json` under profile `demo` requires `draft_warning=true`; `speakers[].label` may be `null` and is never auto-filled |
| `[D0-FIX-01]` | `test_packed_fixtures.py` (`requires_inputs`) | each packed baseline transcript converts via `load_legacy_transcript` into a valid `TranscriptArtifact`; segment count and time bounds are self-consistent |
| `[D0-FIX-02]` | (`requires_inputs`) | a corrupted copy of a converted artifact (`end < start`) fails validation with a non-zero CLI exit |
| `[D0-LEG-01]` | `test_packed_fixtures.py` | conversion maps integer `id` to `s0000`-style ids, preserves `start`/`end`/`speaker`/`text` verbatim, marks blank text as `empty=true`, and leaves the source file byte-identical |
| `[D0-RU-01]` | `test_ru_ratio.py` | ratio on hand-written strings: pure Russian → 1.0; half latin → 0.5; digits and punctuation excluded; `ё`/`е` equivalent; tokens of one character ignored |
| `[D0-RU-02]` | | empty segments contribute nothing and do not divide by zero; latin counter finds `DimaTorzok`-style contamination |
| `[D0-JOB-01]` | `test_jobs_store.py` | `job.json` matches the contract; state transitions `queued→running→done`; events append in order |
| `[D0-JOB-02]` | | raw client IP never appears in `job.json` or logs — only the salted hash; missing `JOB_IP_SALT` fails loudly |
| `[D0-HLT-01]` | `test_health.py` | `GET /healthz` returns 200 and lists per-component status when the environment is sane |
| `[D0-HLT-02]` | | a broken component (unwritable storage root or missing required env var) returns 503 naming that component |
| `[D0-AUD-01]` | `test_probe_audio.py` (`requires_inputs`) | `transcriber probe-audio` on `cloud_in/inputs/audio/test_voice.m4a` exits 0 and reports duration in 80–90 s |
| `[D0-AUD-02]` | | probe on a missing path exits non-zero; D0 must not call ASR on the packed clip |

## Execution

```
uv run pytest tests/ -v
uv run ruff check src/
uv run mypy src/
uv run bandit -r src/ -ll
uv run transcriber plan --job var/jobs/fixture
uv run transcriber healthcheck
```

Lint runs before the verdict; lint failures block the handoff (backend linting rule).

## Report

Write `agent_docs/reports/test_D0.md`: per `[TEST-ID]` expected vs actual with evidence for every
failure and the required @Coder action; on success confirm each acceptance criterion of
`coder_D0.md`. Mirror gate ids G0.0–G0.7 in `cloud_out/gate_D0.md`.

Append to `agent_docs/progress/stage_D0.md`:

```
## YYYY-MM-DD — Tester
- STATUS: TEST_PASS | TEST_FAIL | BLOCKED
- Tests: <paths>
- Executed: <commands and exit codes>
- Report: agent_docs/reports/test_D0.md
```

Verdict to the user in Russian; test code and report body in English.

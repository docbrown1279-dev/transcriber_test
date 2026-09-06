# Coder instructions — stage D3 (insights + report)

Status precondition: `agent_docs/progress/stage_D3.md` contains `INSTRUCTIONS_READY`.
Contracts: [`../contracts/pipeline_artifacts.md`](../contracts/pipeline_artifacts.md) §8–§9,
[`../contracts/module_interfaces.md`](../contracts/module_interfaces.md),
[`../contracts/config_profiles.md`](../contracts/config_profiles.md),
[`../contracts/quality_gates.md`](../contracts/quality_gates.md) (G3),
[`../contracts/llm/`](../contracts/llm/).
Plan: [`../plans/draft_D3_scope.md`](../plans/draft_D3_scope.md),
[`../plans/draft_llm_wrapper.md`](../plans/draft_llm_wrapper.md).
Human manual (do not rewrite; already written): [`../../manuals/llm.md`](../../manuals/llm.md).

Goal: **extract per chapter → one report call → `report.md` renderer**. Default backend Gemini
API. Implement `openai_compat` for NVIDIA/Qwen (config only; live gate uses Gemini). Do **not**
implement `local_llama` / llama.cpp. Do not bakeoff prompts or the 3c “no insights” filter.

Ambiguity → `cloud_out/BLOCKED.md` and stop.

## Scope

Write / modify only these paths (create files that do not exist yet):

```
config/base_llm.yaml                    # copy from agent_docs/contracts/llm/base_llm.yaml
config/llm_extra/                       # only if a backend extra_config is non-null
config/base.yaml                        # drop duplicated llm: block once base_llm.yaml loads
config/profiles/{demo,dev,prod}.yaml    # llm.mode / llm.backend overlays; remove stale provider keys
src/transcriber/config/loader.py        # merge base.yaml ← base_llm.yaml ← profile; optional .env
src/transcriber/config/schema.py        # LlmConfig matching base_llm.yaml (backends, tasks, base_llm)
src/transcriber/llm/base.py             # complete(..., prompt_id, max_tokens|None, temperature|None, json_schema, extra)
src/transcriber/llm/factory.py          # make_client from llm.backends[backend]
src/transcriber/llm/gemini.py           # no hardcoded title schema; schema from the call
src/transcriber/llm/openai_compat.py    # NVIDIA/Qwen via httpx + base_url; no live call required in gate
src/transcriber/llm/prompts.py          # load markdown + JSON schema by path under the llm package
src/transcriber/llm/prompts/chapter_titles/v1.md
src/transcriber/llm/prompts/meeting_insights/v1_extract.md
src/transcriber/llm/prompts/meeting_insights/v1_report.md
src/transcriber/llm/schemas/*.json      # copy from agent_docs/contracts/llm/schemas/
src/transcriber/llm/titles.py           # use llm.tasks.chapter_titles (keep D2 behaviour)
src/transcriber/insights/extract.py
src/transcriber/insights/report.py
src/transcriber/insights/clock_gate.py
src/transcriber/export/markdown.py      # report.json → report.md, no LLM
src/transcriber/quality/checks.py       # G3 helpers
src/transcriber/quality/__main__.py     # check-insights / check-report
src/transcriber/pipeline/steps.py       # insights_extract + report; requires transcript.json
src/transcriber/pipeline/orchestrator.py
src/transcriber/registry.py             # openai_compat real factory; local_llama stays stub
src/transcriber/cli.py                  # run from packed chapters+transcript through report
src/transcriber/web/health.py           # LLM ready if api_key_env for active backend is set (no live call)
pyproject.toml / uv.lock                # httpx in extra llm only
```

Copy prompt/schema **verbatim** from `agent_docs/contracts/llm/`. Keep D2
`src/transcriber/llm/prompts/title_p1_v1.md` as a file until titles read `chapter_titles/v1.md`
(same body).

Do not create `tests/` (Tester). Do not edit `docs/`, `agent_docs/contracts/`, `manuals/`,
`eval/`, `data/`, `.env`, `.cursor/`. No ASR/VAD/chunking. No GGUF. No `llama-cpp-python`.

## Approved dependencies

| Package | Note |
|---|---|
| `google-genai` | already in extra `llm` |
| `httpx` | add to extra `llm` (`uv add --optional llm httpx` or equivalent) — OpenAI-compat transport |

Do **not** add: `openai` SDK, `llama-cpp-python`, Jina, Whisper.

## Algorithm

1. **Config.** `load_config`: deep-merge `base.yaml` ← `base_llm.yaml` ← `profiles/{p}.yaml`.
   Profile `demo`: `llm.mode: api`, `llm.backend: gemini`. Read secret **values** from the
   environment (and `.env` if pydantic-settings / dotenv is already available) using
   `api_key_env` **names** only. Never log values.
2. **Client.** `make_client(cfg.llm)` from `backends[backend]`. Gemini: JSON mime + call-time
   `json_schema`. `openai_compat`: POST to `base_url`, bearer from env. `extra` kwargs only from
   backend `extra_config` (null in the demo yaml).
3. **Merge params** for a call: `base_llm` ← backend ← task step (`max_tokens` etc.). YAML `null`
   → omit the API argument.
4. **Extract** (`meeting_insights.extract`): one call per chapter. Build chapter text and
   `src_catalog` from `source_ids`. Render `{{placeholders}}`. Parse JSON. Hydrate `src` from
   transcript (`segment_id` → start/end/speaker). Unknown id → retry once, then drop that point
   or FAIL the chapter honestly (do not invent ids). Empty `key_points` is valid.
5. **Report** (`meeting_insights.report`): one call on merged insights + chapter index (no full
   ASR dump). Hydrate `key_moments` times from src/segment. `speakers[]` from transcript,
   `label: null`. `chapters[]` copied from `chapters.json`. `draft_warning: true` in demo.
6. **Markdown.** Render `report.json` → `report.md`. Not an LLM call.
7. **Clock-gate** after hydration. Budget: `max_calls_per_job` (40). Exceed → FAIL, do not trim
   silently.
8. **Titles** still work: point D2 titles at `tasks.chapter_titles` so Gemini is no longer
   title-schema-hardcoded.

## Packed run (required)

Inputs: `cloud_in/inputs/artifacts/voice_002/{transcript.json,chapters.json}`.
Outputs: `cloud_out/artifacts/voice_002/{insights.json,report.json,report.md}`.
No audio. No re-chunk. No ASR.

CLI: resume a job dir that already has those two JSON files; run `insights_extract` then `report`.

## Quality CLI

```
python -m transcriber.quality check-insights <insights.json> --chapters … --transcript …
python -m transcriber.quality check-report <report.json> --insights … --chapters …
```

Fill `cloud_out/gate_D3.md` for G3.0–G3.9.

## Budgets

| Block | Cap |
|---|---|
| Gemini calls | ≤40 (14 extract + 1 report + retries) |
| Live NVIDIA/Qwen | 0 required (code + cassette tests only) |
| ASR | **0** |
| Gate fix retries | ≤2, then FAIL + push |

## Stop-list

`eval/`, `.env` (do not open), `data/`, audio, GGUF, llama.cpp, prompt bakeoffs, weakening G3,
force-push, opening a PR, rewriting `transcript.json` / `chapters.json`, `docs/research_results/`.

## Done when

- [ ] `config/base_llm.yaml` loaded; demo backend gemini
- [ ] extract + report + markdown on packed voice_002
- [ ] `openai_compat` constructible; `local_llama` still stub
- [ ] G3 automated checks implemented; agent G3.5/G3.9 filled
- [ ] lint/type/security exit 0; branch `cursor/demo-d3-insights` pushed (no PR)

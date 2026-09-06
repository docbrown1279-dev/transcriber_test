# Gate D2 — chunking and chapter titles
## Verdict: PASS_WITH_WARNINGS
## Checks
| id | check | value | threshold | status |
|---|---|---|---|---|
| G2.0 | Preflight | Packed transcript and stack present; `GEMINI_API_KEY` and `HF_TOKEN` present | All required D2 inputs and secrets present | PASS |
| G2.1 | Chapter times copied from source segments | 16/16 exact | Exact first/last source bounds | PASS |
| G2.2 | Chapters per minute | 0.654 | PASS `[0.4, 0.8]`; WARN `[0.3, 1.0]` | PASS |
| G2.3 | Duration warnings | Short: C00, C06, C07, C11, C12, C14, C15; long: none | List `<45 s` and `>180 s` | WARN |
| G2.4 | Title word count | Maximum 9 words | `<=10` words | PASS |
| G2.5 | Forbidden stamp prefix | 0 titles | No match at title start | PASS |
| G2.6 | Unique non-empty titles | 16 unique, 0 empty | All unique and non-empty | PASS |
| G2.7 | Non-empty source coverage | 268/268 exactly once; 0 gaps, 0 overlaps | Every non-empty segment exactly once | PASS |
| G2.8 | Agent title judgement | 13 hit, 3 generic, 0 miss | At most 1 miss per 12–14 chapters | PASS |

Automated verification:

| command | result |
|---|---|
| `uv run pytest tests/ -v` | PASS: 58 passed, 5 skipped |
| `uv run ruff check src/` | PASS |
| `uv run mypy src/` | PASS: 60 source files |
| `uv run bandit -r src/ -ll` | PASS: no medium/high issues |
| `uv run python -m transcriber.quality check-chapters ...` | PASS_WITH_WARNINGS: only G2.3 |

## Agent judgement
| chapter | title assessment | verdict |
|---|---|---|
| C00 | Accurately identifies protocol feedback | hit |
| C01 | Accurately identifies stormwater connection and runoff accounting | hit |
| C02 | Covers project clarifications and transformer placement, but compresses several subtopics | generic |
| C03 | Accurately identifies technical conditions and approval timing | hit |
| C04 | Accurately combines load calculations and communications-network routing | hit |
| C05 | Accurately identifies network questions and planning documentation | hit |
| C06 | Accurately identifies preparation of plans and sections | hit |
| C07 | Accurately identifies comparison of building characteristics | hit |
| C08 | Accurately identifies layout revisions driven by commercial requirements | hit |
| C09 | Accurately identifies mortgage constraints on apartment mix | hit |
| C10 | Accurately identifies document submission and apartment-mix comments | hit |
| C11 | Accurately identifies market impact from key-rate changes | hit |
| C12 | Matches the brief question about buildings nine and ten, but is linguistically generic | generic |
| C13 | Accurately identifies architect feedback and priority levels | hit |
| C14 | Accurately identifies the meeting closing | hit |
| C15 | Matches the final fragment but necessarily remains generic | generic |

The chapter table of contents is usable. No title is a semantic miss. The seven short chapters are
retained as warnings because the frozen similarity threshold and 180-second merge cap do not allow
an honest additional merge without weakening G2 or inventing a boundary.

## Environment
- Host: Linux 6.12.94+, 4 CPUs, 15 GiB RAM, 247 GiB free workspace disk.
- Python: 3.12.3; ffmpeg: 6.1.1.
- Packages: `sentence-transformers==6.0.1`, `torch==2.14.0+cpu`,
  `google-genai==2.22.0`, `numpy==2.5.2`, `pydantic==2.13.5`.
- Full artifact runtime: 73.702 seconds.
- Repeat chunk measurement: 5.772 seconds; peak RSS 605,792 KiB.
- LLM calls: 18 Gemini calls for titles (2 malformed pre-schema attempts, then 16 successful
  structured-output calls). Text only; no audio was processed or sent.

## Deviations and blockers
- `cloud_in/HANDOFF.md` still describes D1 and branch `cursor/demo-d1-speech`. The explicit user
  request, `cloud_in/prompt.md`, D2 instruction files, packed inputs, and current branch all identify
  D2, so this run followed D2.
- The tester instruction asks for `agent_docs/reports/test_D2.md`, while the user explicitly
  restricted reports to `cloud_out/`; no report was written outside `cloud_out/`.
- The D2 pack intentionally omits D0 baseline files, D0 audio, and D1 speech-chain outputs. Five
  `requires_inputs` tests skipped those unavailable stage-specific fixtures; the required D2
  full-meeting integration test passed.
- Existing D1 gate blockers were repaired minimally: a stale job-stage class name, three static
  analysis findings, and stale D1 T2 config assertions.
- Approved dependencies were already declared in `pyproject.toml`; `uv sync --all-extras` installed
  the existing locked groups. The rubert-tiny2 weights downloaded successfully on the first attempt.
- No blockers remain.

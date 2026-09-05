
# Contract: quality gates (cloud, gold-free)

Draft, Phase A. These gates are the automated part of the human control points from the roadmap.
They run in the cloud, so they must not use `eval/` gold: cloud verdicts are based on the
artifacts themselves plus one explicit agent judgement per stage.

Each stage writes `agent_docs/reports/gate_D{N}.md`: check id, value, threshold, status, plus the
agent judgement section. Verdict `FAIL` stops the stage — thresholds are never adjusted to pass.
`WARN` is reported and does not block.

Reusable implementation: `src/transcriber/quality/` (see `module_interfaces.md` §6).

## G0 — skeleton (stage D0)

| id | Check | Threshold |
|---|---|---|
| G0.0 | Preflight: `cloud_in/agent/{AGENTS.md,rules.md}`, `cloud_in/prompt.md`, `cloud_in/HANDOFF.md` and every file listed under "Inputs" of the prompt are present | all present, otherwise stop with `cloud_out/BLOCKED.md` naming the missing files |
| G0.1 | `uv run pytest tests/ -v` | exit 0 |
| G0.2 | `uv run ruff check src/`, `uv run mypy src/`, `uv run bandit -r src/ -ll` | exit 0 each |
| G0.3 | Registry contains every key from `module_interfaces.md` §3 | all present |
| G0.4 | Every prod-only key raises `ComponentUnavailableError` under profile `demo` | all |
| G0.5 | `transcriber plan` resolves the stage graph for a job seeded with fixture artifacts and prints per-stage status (`done` / `pending` / `unavailable`) | exit 0, order matches the contract |
| G0.6 | `transcriber validate` loads every packed fixture artifact into its pydantic model | exit 0 |
| G0.7 | `GET /healthz` reports the startup self-check per component; includes `ffmpeg`/`ffprobe` success on the packed clip `cloud_in/inputs/audio/test_voice.m4a` (duration within 80–90 s) when that path exists | 200 when config, registry, storage, ffmpeg and probe are fine; non-200 with the failing component otherwise |

D0 implements no model-backed stage: pipeline steps whose engine arrives later must report
`unavailable` through the plan command and raise `StageNotImplementedError` when called. Fixture
or placeholder data must never be written into a production artifact path to make a stage look
complete. Packed audio is for probe/smoke only — no ASR/VAD/diarization in D0.

## G1 — speech recognised (stage D1)

| id | Check | Threshold |
|---|---|---|
| G1.1 | Russian word ratio over all `transcript.json` text | `>= 0.90` — **FAIL** below |
| G1.2 | Latin characters inside segment text | `== 0` — FAIL otherwise (stage 1e: whisper artefact, GigaAM gives 0) |
| G1.3 | `transcript.json` / `quality.json` validate against models | valid |
| G1.4 | Segment times monotonic, inside audio duration, `end > start` | all |
| G1.5 | Holes `>= min_hole_sec` and empty segments enumerated in the artifact | present (WARN only if many) |
| G1.6 | Wall time and peak RSS per stage recorded | present |
| G1.7 | Agent judgement: 3–5 random ~2-sentence fragments are coherent Russian speech | agent verdict `pass` |

Ratio definition: tokens are `\w+` sequences with `>= 2` characters, lowercased, `ё → е`;
a token counts as Russian when all characters are Cyrillic. Ratio = russian tokens / all tokens.
Numbers and punctuation are excluded from both sides. Empty segments contribute nothing.

## G2 — chapters and titles (stage D2)

| id | Check | Threshold |
|---|---|---|
| G2.1 | Chapter times copied from segment boundaries (`start` of first, `end` of last `source_ids`) | exact match, FAIL otherwise |
| G2.2 | `chapters_per_minute` | inside `[0.4, 0.8]` → pass; `[0.3, 1.0]` → WARN; outside → FAIL |
| G2.3 | Chapters shorter than 45 s / longer than 180 s | listed, WARN |
| G2.4 | `title` word count | `<= 10`, FAIL otherwise |
| G2.5 | `title` does not start with a stamp phrase | FAIL on match |
| G2.6 | Titles unique, non-empty, no raw ASR garbage token repeated verbatim from the first sentence | FAIL on duplicates/empty |
| G2.7 | `source_ids` cover every non-empty segment exactly once | FAIL on gaps/overlaps |
| G2.8 | Agent judgement: for each chapter, does the title match the content — `hit` / `generic` / `miss` | `miss <= 1` per 12–14 chapters |

Stamp phrases (case-insensitive, at title start): `обсуждение`, `обсудили`, `говорили о`,
`совещание по`, `разговор о`. Rationale: stage 3 showed P2 titles copying the first sentence and
P1 producing one `обсуждение` title.

## G3 — insights and report (stage D3)

| id | Check | Threshold |
|---|---|---|
| G3.1 | Clock-gate: every `start`/`end` in `insights.json` and `report.json` exists in `chapters.json` or in the referenced segment | `mismatch == 0`, FAIL otherwise |
| G3.2 | Every `src.segment_id` exists and belongs to the same chapter | FAIL otherwise |
| G3.3 | Every `key_point` has non-empty `src` | FAIL otherwise |
| G3.4 | Digit groups in `key_points` occur in the chapter source text | FAIL on invented numbers |
| G3.5 | `actions` / `open_questions` empty unless the chapter text contains them | agent-checked, FAIL on invented owners or tasks |
| G3.6 | `key_moments` count in `report.json` | `5..12`, WARN outside |
| G3.7 | No `key_point` or summary sentence starts with a stamp phrase | FAIL on match |
| G3.8 | `draft_warning == true` in profile demo | FAIL otherwise |
| G3.9 | Agent judgement: share of key points that are verifiable facts (decision, number, condition, agreement) vs filler | `>= 60%` verifiable |

G3.9 exists because stage 3c could not tune the "insight bar" with prompt text alone; the number is
a reporting bar for the human gate, not a claim of solved quality.

## G4 — web demo (stage D4)

| id | Check | Threshold |
|---|---|---|
| G4.1 | `uv run pytest tests/ -v` incl. E2E upload → progress → result → download on the 85 s clip from `cloud_in/inputs/audio/` | exit 0 |
| G4.2 | `GET /healthz` | 200, lists per-component status from the startup self-check |
| G4.3 | Second request from the same IP within 24 h | 429 with a human-readable message |
| G4.4 | Second concurrent job | rejected, queue never exceeds `queue_max_size` |
| G4.5 | File over `max_file_size_mb` / audio over `max_minutes` | rejected before the pipeline starts |
| G4.6 | TTL sweeper removes the job directory including the upload | directory absent after expiry |
| G4.7 | Logs contain no transcript text and no secret values | grep-based check, FAIL on match |
| G4.8 | Result page renders summary, key moments with timecodes, chapters, download link | asserted in E2E |

## G5 — demo hardware (stage D5)

| id | Check | Threshold |
|---|---|---|
| G5.1 | Docker run `--cpus=2 --memory=8g` on a 15-minute slice | completes, no OOM kill |
| G5.2 | Per-stage wall time and peak RSS report | present |
| G5.3 | Total wall time for 15 minutes of audio | reported; if unacceptable, recommend lowering `audio.max_minutes` to 10 (spec §3 allows it) |
| G5.4 | Peak RSS of the web process while a job runs | `< 7 GiB` including the ASR subprocess |

## Cloud restrictions during gates

- Inputs come from `cloud_in/inputs/` only; outputs of the gate go to `cloud_out/gate_D{N}.md`
  plus `cloud_out/run_meta.json` (branch, commit, wall time, LLM calls, versions).
- `eval/` must not be read, copied, or referenced in any gate, prompt, or report. Neither must
  `.env`.
- The full 24-minute recording is not processed in the cloud; the packed clips and one
  15-minute slice (D5 only) are the allowed inputs.
- Audio is never sent to an LLM API — text only, as in the research stages.
- LLM in the cloud is `gemini` only; `local_llama` is never run there. Calls per cloud run:
  `<= 20`, each recorded in the gate report as provider + purpose, never the key.

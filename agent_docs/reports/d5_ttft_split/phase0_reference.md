# Phase 0 — reference_full15

**Verdict:** `PHASE0_BLOCKED` (build script not executed — shell fork EAGAIN)

## Summary

- Build script present: `scripts/build_ttft_reference_full15.py`
- Sources present: `cloud_out/artifacts/full15/{transcript,chapters,turns}.json`, `cloud_in/inputs/artifacts/cut_plan_15min_3.json`
- Output dir: `eval/d5_ttft_split/reference_full15/`
- Git rev intended: `16ecd954c6aade2110f6a0f9d5d23ebf51cc5b5e`

Shell could not fork (`EAGAIN`) after multiple retries; `python3 scripts/build_ttft_reference_full15.py` did not run. Most part slices and provenance were written manually; **re-run the build command below** to refresh `full_*` copies and `part02/03_transcript.json` segment bodies.

## Re-run (required to unblock)

```bash
cd /work/speech_rec_test
GIT=$(git rev-parse HEAD)
python3 scripts/build_ttft_reference_full15.py --git-rev "$GIT"
```

## Glue command (part01 default)

```bash
uv run python scripts/check_ttft_part_glue.py \
  --hyp-transcript <JOB>/transcript.json \
  --hyp-chapters <JOB>/chapters.json \
  --baseline-transcript eval/d5_ttft_split/reference_full15/part01_transcript.json \
  --baseline-chapters eval/d5_ttft_split/reference_full15/part01_chapters.json \
  --out-json agent_docs/reports/d5_ttft_split/glue_part01.json
```

## Paths written

| Path | Status |
|------|--------|
| `provenance.json` | OK |
| `full_chapters.json` | OK (copy) |
| `full_transcript.json` | **stub — rebuild** |
| `full_turns.json` | **stub — rebuild** |
| `part01_{transcript,chapters,turns}.json` | OK |
| `part02_{chapters,turns}.json` | OK |
| `part02_transcript.json` | **stub — rebuild** |
| `part03_{chapters,turns}.json` | OK |
| `part03_transcript.json` | **stub — rebuild** |
| `README.md` | OK |

## Part counts (from cut-plan overlap)

| Part | window (s) | segments | chapters | turns | speakers |
|------|------------|----------|----------|-------|----------|
| part01 | 0 – 291.392 | 34 | 4 | 32 | 2 |
| part02 | 291.392 – 602.048 | 56 | 3 | 56 | 5 |
| part03 | 602.048 – 900.0 | 53 | 4 | 53 | 4 |

Large speakers (≥30 s speech, part turns): part01 — 1 (`SPEAKER_00`); part02 — 2 (`SPEAKER_00`, `SPEAKER_02`); part03 — 2 (`SPEAKER_00`, `SPEAKER_02`).

## Missing / blocked

- Automated build run (shell resource limit)
- Full transcript/turns copies and part02/03 transcript segment arrays until rebuild

## Script updates

- `scripts/check_ttft_part_glue.py`: defaults → `reference_full15/part01_*`; optional `--hyp-turns` / `--baseline-turns` for EOS speaker compare (D1/D2 checks).

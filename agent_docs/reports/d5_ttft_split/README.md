# D5 TTFT file-split — local prep

## Cut plans (Silero pauses from `voice_002_diar_fix` speech.json)

| Plan | Audio | Parts | Part01 | In range 3–6 min |
|---|---|---:|---:|---|
| `cut_plan_15min_3` | 15′ slice | 3 | **291.4 s (~4.9 min)** | YES |
| `cut_plan_15min_4` | 15′ slice | 4 | 229.3 s | YES |
| `cut_plan_full_5` | full ~24.5′ | 5 | **291.4 s** (same first cut) | YES |

Recommended for cloud TTFT spike: **15′ / 3 parts** (matches G5 field audio). Script:
`scripts/plan_pause_cuts.py`.

## Local eval baseline

`eval/d5_ttft_split/` (gitignored) — prior transcript/chapters window for **glue** check, not gold.
See README there + `scripts/check_ttft_part_glue.py`.

## Cloud pack

Branch `cursor/d5-ttft-split`, pack under `cloud_in/` (15′ audio + cut plan + prompt).
Backend `src/` untouched until glue PASS.

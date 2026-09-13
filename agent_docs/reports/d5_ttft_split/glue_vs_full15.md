# Glue / quality vs `reference_full15` (Phase 3)

| Field | Value |
|-------|-------|
| Hyp job | `var/bench/d5/ttft_split_g5` (EOS after 4-part TTFT split) |
| Reference | `eval/d5_ttft_split/reference_full15/` (full15 sliced by **3**-part cut_plan_15min_3) |
| Cut mismatch | Product run: 4 parts `[0,229.3),[229.3,462.9),[462.9,691.4),[691.4,900.1)`; reference: 3 parts ending 291.4 / 602.0 / 900.0 |

## [D5T-Q-01] Large speakers after EOS

| Source | Speakers with speech ≥ 30 s |
|--------|-----------------------------|
| Hyp `turns.json` | **3**: SPEAKER_00 (575.5 s), SPEAKER_02 (107.7 s), SPEAKER_01 (84.2 s) |
| Reference `full_turns.json` | **3**: same ids / durations (ballpark match) |

**PASS** — not collapsed to 2 large speakers.

## [D5T-Q-02] Glue / text coverage

Naive glue of **full** hyp vs each part baseline fails T3/C3/C4 (full timeline vs part window) — expected apples-to-oranges.

**Windowed** hyp (segments/chapters/turns clipped to reference part `[start,end]`) → `glue_*_windowed.json`:

| Part | Verdict | Text (T4/T5) | Chapter spill (C3) |
|------|---------|--------------|--------------------|
| part01 | FAIL (1) | PASS coverage=1.000 ratio=1.004 | FAIL max_end=346.5 > 291.4 (chapter straddles cut) |
| part02 | FAIL (1) | PASS coverage=0.970 ratio=1.023 | FAIL max_end=689.6 > 602.0 (same) |
| part03 | **PASS** | PASS coverage=0.996 ratio=0.996 | PASS |

Interpretation per tester instructions: packing / chapter-boundary differences → **WARN**; dropped half of text → FAIL. Text coverage stays ≥ 0.97 → **no text-drop FAIL**.

Raw (non-windowed) outputs kept as `glue_part0{1,2,3}.json` for audit.

## [D5T-Q-03] Hotspot abs [365.0, 375.5] after EOS

| Speaker | Interval | Transcript snippet |
|---------|----------|--------------------|
| SPEAKER_03 | 365.20–365.95 | «так» |
| SPEAKER_02 | 365.95–375.28 | «и вот есть… кабель пойдет… через двор / паркинг…» |

Cable/hotspot speech attributed mainly to SPEAKER_02 after EOS. Human listen optional (`HUMAN_GATE`) — not run.

## [D5T-Q-04] Mid-run id flicker

Not gated. Mid-run may flicker; EOS large-speaker count ≥ 3 satisfied.

## Phase 3 summary

**PASS_WITH_WARNINGS** — EOS speakers OK; text coverage OK; chapter C3 spill + 4-vs-3 cut plan documented as packing/cut WARN only.

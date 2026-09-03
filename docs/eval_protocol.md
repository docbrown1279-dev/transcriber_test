# How we score ASR (no gold in git)

Human reference lives only in **`eval/gold.json`** (gitignored). Cloud agents clone GitHub and **must not** receive this file.

Committed here: format + metrics. Copy `eval/gold.example.json` → `eval/gold.json` locally and edit while listening.

## What to annotate

| Field | Need it? |
|---|---|
| `text` | Yes — main quality signal (WER) |
| `start` / `end` (seconds) | Yes if we care about alignment / player UX / diarization |
| `speaker` | Yes for Stage 1b (`SPEAKER_00` or `A`/`B`) |

You do **not** need frame-perfect cuts. A **collar** (ignore zone) around boundaries is standard.

## Metrics (closest CV analogues)

There is no official “mAP for Whisper”, but the time-axis analogue of box IoU / mAP is well defined.

### 1. Text — WER (primary)

Word Error Rate after light normalization (lowercase, ё→е, strip punctuation):

`WER = (S + D + I) / N`

Same role as classification error, not mAP.

### 2. Time — temporal IoU (like bbox IoU)

For a matched gold interval `G` and prediction `P`:

`tIoU = |G ∩ P| / |G ∪ P|`

Example: gold 1.1–3.5 vs pred 1.2–3.6 → overlap 2.3 s, union 2.5 s → **tIoU = 0.92** (a hit).

**Hit rule (VOC-like):** `tIoU ≥ 0.5` (strict: 0.75).

**Collar (NIST diarization, usually 0.25 s):** do not penalize start/end if they are within ±0.25 s (or 0.5 s for coarse meeting notes). Your 0.1 s shift is **inside** a 0.25 s collar — counts as aligned.

### 3. Phrase detection — t-mAP (optional, COCO-like)

Treat each gold phrase as a 1-D “object” on the time axis. Predictions are detections.

- Match if text is close enough **and** `tIoU ≥ t`
- Average precision at `t ∈ {0.50, 0.55, …, 0.95}` → **t-mAP**

On **one** meeting this is just precision/recall at those thresholds (all scores = 1 if the model has no confidences). Useful later with many files. For now: **recall@tIoU=0.5** + median timing error is enough.

### 4. Speakers — DER (not mAP)

Diarization Error Rate = missed speech + false alarm + speaker confusion, typically with **0.25 s collar** (`pyannote.metrics`). This is the standard, not mAP.

### 5. Timestamped WER (stricter)

A gold word counts as correct only if the **word text** matches **and** its timestamp is within the collar. Use when the player must highlight the right word.

## Recommended tolerances for this project

| Check | Default |
|---|---|
| Text | WER on normalized words |
| Phrase time | collar **0.25 s** *or* tIoU **≥ 0.5** |
| Speakers | DER, collar **0.25 s** |

Do not fail a run because 1.1–3.5 became 1.2–3.6.

## Local score

After `eval/gold.json` exists:

```bash
python3 scripts/eval_against_gold.py results/asr/some_hypothesis.json
```

If `eval/gold.json` is missing, the script exits without scoring (safe on a cloud clone).

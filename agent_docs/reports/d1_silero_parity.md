# D1 — Silero parity with research 1f

**Branch:** `cursor/d1-silero-parity`  
**Ticket:** `agent_docs/plans/ticket_d1_silero_parity.md`  
**Date:** 2026-09-05

## Verdict (step 1)

**Parity on `test_voice` accepted.** With snakers4 Silero weights + v5 context window + 1f timestamping, raw VAD (no dynaudnorm) recovers the 1f speech mask and near-identical GigaAM text on 0–75 s. Current `data/voice_002/` remains clearly worse («определено точ», glued speakers, missing mid expertise).

## Root causes (why demo ≠ 1f)

| # | Issue | Effect |
|---|---|---|
| 1 | `models/silero_vad.onnx` was **deepghs** fork (sha `2623a295…`), not **snakers4** (`1a153a22…`) | Quiet mid-clip speech (≈21–40 s) almost invisible to VAD |
| 2 | `SileroVadDetector` fed bare 512-sample chunks **without 64-sample context** | Even with snakers4 weights, probs collapse on soft speech |
| 3 | Timestamp loop ≠ 1f `speech_timestamps` (no `speech_pad`, different silence end) | Region boundaries drift |
| 4 | Ticket sketch said thr 0.5 / `min_silence` 200; **actual 1f** used thr **0.45**, `min_silence_ms` **50** | Documented; parity uses 1f code defaults |

Config deviations (dynaudnorm C3 + merge agg) were secondary once VAD was broken.

## Fixes in this branch

- Replace ONNX with snakers4 weights under `models/silero_vad.onnx` (deepghs copy in `.trash/silero_model_backup/`).
- Rewrite `src/transcriber/vad/silero.py`: context window, 1f timestamping, download URL → snakers4 GitHub raw.
- Overlay / runner: `config/profiles/d1_parity_1f.yaml`, `scripts/run_d1_parity_1f.py` (demo profile + overrides; registry has no custom profile name).

## Step 1 metrics — `test_voice`

| | speech_sec | VAD regions | notes |
|---|---:|---:|---|
| 1f recovered raw_turns | 62.376 | 29 | etalon |
| parity VAD (this run) | 62.376 | 29 | **exact match** of region starts/ends |
| voice_002 (demo) | ~55.8 on 0–75 | — | dynaudnorm + merge agg |

### Side-by-side text 0–75 s (abridged)

| t | 1f recovered | parity T0 | voice_002 now |
|---|---|---|---|
| ~0–4 | давайте по протоколу есть | same | mixed / truncated |
| ~14–21 | ну направим пару вопросов… | same | glued with previous |
| ~26–35 | це от / надо нести / **определено точки подключения** | same | **определено точ** |
| ~35–51 | …заходим/заболет экспертизу… плюс минус… ссылаться на их проект | same (заходим) | mid cut, missing glue |
| ~55–65 | заключение экспертизы / вопрос закрое(м) | same | speaker glue onto next Q |

Residual vs 1f (not blockers):

- Extra crumb `содном газ` ~4.6–5.3 s (WeSpeaker oversplit vs 1f Spectral cluster).
- Speaker id remap (`SPEAKER_02` vs `SPEAKER_01`) — demo uses AgglomerativeClustering thr 0.80, 1f used Spectral/GMM.
- Tiny ASR diffs (`заболет`↔`заходим`, `закон`↔`закрое`).

## Other clips (T0)

| clip | speech_sec | nonempty ASR | ref JSON |
|---|---:|---:|---|
| test_apartments | 63.1 | 23 | present — readable, not byte-identical |
| test_transformers | 65.9 | 20 | no recovered JSON in `data/research_asr_1f_vad_wespeaker/` |
| test_ninth | 64.8 | 20 | no recovered JSON |

Artifacts: `results/d1_parity_1f/{clip}/`.

## Step 2 — soft tunes (done on test_voice)

| id | change | speech_sec | turns | human read (canalization+expertise) |
|---|---|---:|---:|---|
| T0 | parity baseline | 62.4 | 15 | Correct lemmas (`точки подключения`, expertise paragraph) but still crumbs «це от» / «надо нести» |
| T1 | `alimiter=limit=-1dB` on vad_input | 53.1 | 13 | **Worse** — lost cover, junk «ресурсника»; peak-only not enough for quiet speech |
| T2 | `min_silence_ms=350` + `vad_premerge_gap=0.5` | 66.6 | 9 | **Best readability** — one turn «надо через паркинг… определено точками подключения… экспертизу…» |

**Tune verdict:** keep **T0 as regression baseline**; prefer **T2** as candidate demo defaults over C3 dynaudnorm. Do **not** ship T1. Still no dynaudnorm on whole file.

## Step 3 — alternatives

| option | 1f status | recommendation after T0/T2 |
|---|---|---|
| sherpa + `cluster_threshold` nudge | seg IoU ~0.94; 5–8 speakers at 0.5 | **defer** — Silero+T2 already readable; sherpa only if speaker id purity blocks packing |
| standalone pyannote-onnx-extended / embedding-onnx | **not tested in 1f** | **defer** — needs separate CPU budget / approval |
| TEN/FSMN hole-fill | 1f2 conclusions | optional later for residual holes only |

## Commands

```bash
export HF_HUB_OFFLINE=1
.venv/bin/python scripts/run_d1_parity_1f.py          # all 4 clips
.venv/bin/python scripts/run_d1_parity_1f.py test_voice
```

## Soft tunes (T0/T1/T2) — test_voice

| id | vad_pp | speech_sec | turns | canalization 25–36 | expertise 35–52 |
|---|---|---:|---:|---|---|
| `T0` | off | 62.4 | 15 | це от | надо нести | определено точки подключения | ориентируется на проект как  | ориентируется на проект как я и написал что сейчас этот проект там ну в ближайше |
| `T1` | alimiter=limit=-1dB:level=false | 53.1 | 13 | надо нести | определено точки подключения | ресурсника | ориентируются на проект | ориентируются на проект как я и написал что сейчас проект там ну в ближайшее вре |
| `T2` | off | 66.6 | 9 | надо через паркинг потому что это определено точками подключения ориентироваться | то есть проект у вас уже есть как появится положительное заключение я думаю к эт |

Artifacts: `results/d1_parity_tune/`.

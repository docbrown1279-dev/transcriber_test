# D4.1 Phase 1 — A vs B (10 min voice_002)

**Status:** CLOSED on `main` (`pipeline.toc_mode: b` default; `a` = batch fallback)  
**Audio:** `var/bench/d4_1/voice_002_10min.m4a` (600 s)  
**Seed diarization:** Phase 0 job (A/B title paths did not re-run diarize)

## Phase 0

Sequential baseline: normalize→vad→diar→asr→chunk→**1 LLM call per chapter**.

## Results (final B = title when next chapter appears)

| metric | baseline (seq titles) | **A** batch titles | **B** slice∥API (fixed) |
|---|---:|---:|---:|
| titles LLM calls | 6 | **1** | **6** |
| titles wall (sec) | ~15.26 | **6.863** | overlapped with ASR |
| time to first titled chapter (from ASR start) | ~59 | ~63 | **19.969** |
| ASR+titles total (from turns ready) | ~72 | ~63 | **119.247** |
| peak RSS (MiB) | ~1693 | 57.7 (titles-only) | 1956.0 |
| chapters | 6 | 6 | 6 |

Note: earlier B draft had **14** LLM calls (fingerprint re-fire). Fixed to slot-based close-on-next-chapter → **6** calls. Total wall is ASR-dominated (~109s ASR); 6 vs 14 calls does not explain wall variance.

### Mode A titles
- Подключение ливневой канализации к сети УДС
- Учёт нагрузок от ливневых стоков в проекте
- Проверка решений по ливневой канализации
- Размещение светильников и магистральные сети
- Согласование изменений в технических условиях с Оборонэнерго
- Расчёт нагрузок на жилые помещения

### Mode B titles (final)
- Обратная связь и уточняющие вопросы
- Учет площади застройки и озеленения
- Проверка решений разработчиков
- Ландшафтная концепция и размещение светильников
- Прокладка кабеля и согласование с Оборонэнерго
- Расчет мощности на квартиру

## Decision (shipped)

- **Default:** `pipeline.toc_mode: b` (streaming titles).
- **Fallback:** `pipeline.toc_mode: a` (full ASR → batch titles) if races/quality issues.
- Bench: `uv run python scripts/bench_d4_1.py --mode a|b ...`
- Backlog: `ticket_d4_1_title_batch2.md` (first title then batches of 2).

## Artifacts

- `baseline_unconstrained.md` / `.json`
- `mode_a.json`, `mode_b.json` (final B)
- `gate_D4_1.md`

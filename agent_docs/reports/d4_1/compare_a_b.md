# D4.1 Phase 1 — A vs B (10 min voice_002)

**Branch:** `cursor/demo-d4-1-perf`  
**Audio:** `var/bench/d4_1/voice_002_10min.m4a` (600 s)  
**Seed diarization:** from Phase 0 job (not re-run for A/B title paths)

## What Phase 0 was

Yes — **fully sequential** current pipeline: normalize→vad→diar→asr→chunk→**1 LLM call per chapter**.

## Results

| metric | baseline (seq titles) | **A** batch titles | **B** slice∥API |
|---|---:|---:|---:|
| titles LLM calls | 6 | **1** | 14 |
| titles wall (sec) | ~15.26 | **6.863** | (overlapped) |
| time to first titled chapter (from ASR start) | ~ASR+first call (~56.333+2.5 ≈ 59) | ASR then batch (~56.333+7 ≈ 63) | **24.474** |
| ASR+titles total (from turns ready) | ~72 | ~63 | **105.103** |
| peak RSS (MiB) | ~1693 | 57.7 (titles-only process) | 1959.5 |
| chapters | 6 | 6 | 6 |

### Mode A titles
- Подключение ливневой канализации к сети УДС
- Учёт нагрузок от ливневых стоков в проекте
- Проверка решений по ливневой канализации
- Размещение светильников и магистральные сети
- Согласование изменений в технических условиях с Оборонэнерго
- Расчёт нагрузок на жилые помещения

### Mode B titles
- Подключение к ливневой канализации УДС
- Учет площади застройки и озеленения
- Проверка решений разработчиков
- Ландшафтная концепция и размещение светильников (3)
- Подключение кабеля и распределение нагрузки по корпусам
- Расчет нагрузки на квартиру (2)

## Interpretation

1. **A works as designed:** 6→1 call, titles wall **15s → 6.9s**. Best default for demo cost/latency when TOC is shown after full ASR.
2. **B proves TTFT:** first titled chapter at **~24s** while ASR continues — UX win for streaming TOC.
3. **B call inflation (14 vs 6):** incremental commits fire titles for chapter fingerprints that later change / get absorbed; local `(2)`/`(3)` suffixes appear. Needs stricter commit rule (e.g. only title when duration ≥ `target_chapter_sec[0]` ≈45s, or title once at true chapter close).
4. **B ASR wall ~95s** > baseline ASR ~56s: in-process GigaAM + rubert between slices (no subprocess isolation); peak RSS ~2 GiB.
5. On this 10 min clip, **A wins total wall** after speech; **B wins time-to-first-title**.

## Recommendation (demo)

- **Default now:** mode **A** (batch titles) after full ASR/chunk — ship in main path via `llm.titles_mode: batch`.
- **Keep B** as experimental path for streaming UI; fix commit/dedupe before making it default.
- D5 cgroup 2/8: re-measure A first; B only after call-count fix.

## Artifacts

- `baseline_unconstrained.md` / `.json`
- `mode_a.json` — job `var/bench/d4_1/job_mode_a`
- `mode_b.json` — job `var/bench/d4_1/job_mode_b`
- Bench: `uv run python scripts/bench_d4_1.py --mode a|b ...`

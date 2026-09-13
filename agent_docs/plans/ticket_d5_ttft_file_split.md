# Тикет: TTFT — разрез файла + якорь центроидов (S2)

**Статус:** CLOSED (2026-09-13) — product file-split in demo (`pipeline.ttft_split`); gate **PASS_WITH_WARNINGS** (`product_gate.md`: TTFT ≈169 s ≤300 @ 2 CPU / 8 GiB).  
**Приоритет:** —  
**Ветка:** `cursor/d5-ttft-split` → merge `main`  
**Спека направления:** [`draft_ttft_diarize_split.md`](draft_ttft_diarize_split.md)  
**Отчёт:** [`../reports/d5_ttft_split/product_gate.md`](../reports/d5_ttft_split/product_gate.md)

---

## Зачем

При фиксированной точности **2A** (WeSpeaker `1.5/0.75` + AHC `0.85`) полный diarize wall ≈ пропорционален речи × окна.  
**TTFT** режем разрезом: part1 → ранняя глава, part2 assign к центроидам part1.

Поле: 15′ @ 2 vCPU ≈ **10:37** полный прогон; цель первой главы **~5–6 мин**.

---

## Исходники research (контекст, не дублировать bakeoff)

| Тема | Результат / где |
|---|---|
| Embed, не cluster = тормоз | [`ticket_d5_diarize_speed.md`](ticket_d5_diarize_speed.md); twopass `timing_5min` |
| Грубые окна 3.0/1.5 | ~6% на 5′ — **отказ** (`cursor/d5-diar-spectral`) |
| Spectral / hybrid / cheap 1B/1C | не замена 2A по gold |
| 2C+AHC0.85 / unit-tune | **SKIPPED** — [`ticket_d5_diar_unit_ahc_tune.md`](ticket_d5_diar_unit_ahc_tune.md) |
| Оркестрация | [`ticket_d5_ttft_experiments.md`](ticket_d5_ttft_experiments.md) |
| Eval + gold | `eval/d5_diar/` (локально) |

---

## Scope (когда откроем)

1. VAD целиком → cut ~40–60% (longest pause / midpoint).  
2. Part1: WeSpeaker **2A** → ASR → packing/titles → **ранний UI**.  
3. Part2: embed хвоста → **assign к центроидам part1** (+ порог нового спикера).  
4. Один writer артефактов; remap `SPEAKER_*`; без live partial TOC с дырами.  
5. Опционально после merge: крошки id на длинных → nearest centroid.

**Не в этом тикете:** Jina / packing D; pyannote; окна 3.0/1.5; H0 model warmup; UI preload (см. [`ticket_d5_ui_upload_progress.md`](ticket_d5_ui_upload_progress.md)).

---

## Gate (черновик)

| Метрика | Цель |
|---|---|
| TTFT (первая usable `chapters.json`, titles optional) | ≤ **300 с** на 15′ @ 2 CPU / 8 GiB (warm) |
| Крупные спикеры part1→full | id стабильны (якорь) |
| Качество vs 2A full | не хуже заметно на gold / глаз на job |

---

## Definition of done

- [x] Unit-tune закрыт: SKIPPED  
- [x] Спека merge+anchor → coder instructions (`coder_D5_ttft.md`; mid = assign B, EOS = V1)  
- [x] Bench TTFT на 15′ @ 2 CPU / 8 GiB ≤ 300 с (`ttft_first_chapter_sec≈169`)  
- [x] Отчёт: TTFT, стабильность id, EOS vs full15; H1/V2 не в mid  
- **Backlog (не блокер):** UI status/ETA poll «подтупливает» — [`ticket_d5_ui_upload_progress.md`](ticket_d5_ui_upload_progress.md)  


# Тикет: TTFT — разрез файла + якорь центроидов (S2)

**Статус:** OPEN — **IN PROGRESS** research spike (part1 only; `src/` still frozen)  
**Приоритет:** высокий для TTFT  
**Ветка:** `cursor/d5-ttft-split` (от `main`)  
**Спека направления:** [`draft_ttft_diarize_split.md`](draft_ttft_diarize_split.md)  
**Локальный prep:** [`../reports/d5_ttft_split/README.md`](../reports/d5_ttft_split/README.md) · cut `cut_plan_15min_3` · eval glue `eval/d5_ttft_split/`

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
| TTFT (первая titled-глава) | ≤ 300–360 с на 15′ @ 2 CPU (warm) |
| Крупные спикеры part1→full | id стабильны (якорь) |
| Качество vs 2A full | не хуже заметно на gold / глаз на job |

---

## Definition of done

- [x] Unit-tune закрыт: SKIPPED  
- [ ] Спека merge+anchor → coder (после research OK)  
- [ ] Bench TTFT на 15′  
- [ ] Отчёт: TTFT, стабильность id, вердикт C+split vs нужен B/Jina  

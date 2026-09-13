# План: TTFT file-split → продукт (по итогам research)

**Статус:** INSTRUCTIONS_READY — bug-fixer / Coder: [`../instructions/coder_D5_ttft.md`](../instructions/coder_D5_ttft.md); Tester: [`../instructions/tester_D5_ttft.md`](../instructions/tester_D5_ttft.md); контракт: [`../contracts/ttft_split.md`](../contracts/ttft_split.md). **TTFT ≤ 300 с** на 15′ @ 2 CPU / 8 GiB.  
**Ветка research:** `cursor/d5-ttft-split`  
**Опора:** unified gain + shared VAD; mid = assign+absorb (B); EOS = V1 AHC на всех эмбеддингах (~98.5% vs full15)  
**Не делать в этом плане:** H1/V2 cluster-match online (схлопывает 3→2 спикеров); sticky; новые diar bakeoff’ы

---

## Зачем

Сократить TTFT: первая usable глава после **part1** (~4–6 мин речи), не после полного diarize+ASR+TOC.  
Качество спикеров в UI сначала **промежуточное**; в конце — уточнение одним AHC по всем векторам (как full).

## Зафиксированные решения research

| Тема | Решение |
|---|---|
| VAD | **Один** прогон на весь файл; куски режут **регионы**, не свой VAD |
| Gain файла | **Один** loudness на весь файл; slice wav уже после gain |
| Потолок gain | **≤ 2 dB** (новый/явный лимит в config; сейчас `audio.gain.max_db: 18` — слишком щедро для file-unify) |
| Per-turn ASR gain | оставить `asr_per_turn_gain: true` (это не file gain) |
| Разрез | паузы Silero, целевая длина куска **~4–6 мин** (`plan_pause_cuts` / cut_plan) |
| Mid diar (B) | part1 = AHC; дальше = **nearest centroid**, `dist ≤ 0.85` → id, иначе **new id**; merge **absorb &lt; 1 s** |
| Online H1 match | **не** брать в продукт (теряет 3-го спикера) |
| EOS | один AHC на **всех** window-эмбеддингах parts (= V1); затем remap id к уже показанным, где возможно |
| LLM titles | батч готовых глав; не блокировать выдачу part1 |
| Правка спикеров в UI | **заблокировать** до EOS refine |

---

## Уточнения к формулировке (зафиксировать так)

1. **«Диаризация отдельно по кускам»** ≠ независимый AHC на каждом.  
   Part1: полный AHC → gallery. Part2+: только embed + **assign к gallery** (+ new id). Иначе снова разъезд id.

2. **Метод B** = исходный тикетный assign (**A**) + absorb крошек &lt; 1 s (**B** в таблице кандидатов). Не H1.

3. **«Последний кусок не трогаем»** = packing: незакрытая глава / tail сегментов **держится**, пока не пришёл следующий part (уже было в split3 packing continuity).

4. **EOS «полная кластеризация»** = AHC по сохранённым эмбеддингам всех parts (не обязателен повторный embed, если векторы сохранены). Remap: стабилизировать id относительно part1/UI.

5. **Eval «gold»** = **не** ручной `eval/d5_diar/gold`. Референс = артефакты **full15** (или повторный full-прогон): turns/transcript/chapters → нарезать теми же cut’ами в `eval/d5_ttft_split/` (gitignored). Скрипт-заготовка: `scripts/check_ttft_part_glue.py`.

---

## Целевой пайплайн (логика продукта)

```
audio
  → normalize once (gain ≤ 2 dB) + VAD once
  → pause-cut → parts[~4–6 min]
  → for each part:
        diarize (part1 AHC | else assign+absorb)
        ASR turns
        chapter embeddings + packing (hold open tail)
        if part1 done → publish early TOC/chapters (speakers read-only)
  → batch LLM titles for ready chapters
  → EOS: AHC(all embeddings) → remap speakers → final turns/chapters (± re-title if boundaries moved)
```

### Шаги 0–7 (как в ТЗ)

| # | Шаг | Детали реализации |
|---|---|---|
| 0 | Shared VAD + unified gain | Config: e.g. `audio.gain.file_max_db: 2.0` (или снизить `max_db` только для file-path). Один `normalized.wav`, потом slice. |
| 1 | Cut 4–6 мин | `scripts/plan_pause_cuts.py` логика → в `src` (сервис cut). План на паузах, fallback midpoint. |
| 2 | Diar per part, same gain | Вход = slice уже нормализованного wav + slice speech.json. |
| 3 | Кластеры методом B | Gallery после part1; assign thr=`cluster_distance_threshold` (0.85); `absorb_turn_shorter_than_sec: 1.0`. |
| 4 | ASR + chunk embeddings | После diar part; packing C; **не закрывать** хвост главы до next part / EOS. |
| 5 | LLM titles батчем | Когда есть закрытые главы; part1 может уйти с placeholder/без title по текущему toc_mode. |
| 6 | Выдача после part1 | TTFT = first titled-or-structured chapter; **speaker edit locked** до EOS. |
| 7 | EOS refine | V1 AHC all windows → update speaker labels (и при необходимости merge turns); UI unlock. |

---

## Этапы работ для фиксика

### Phase 0 — Eval reference (локально, до/параллельно коду)

1. Взять `cloud_out/artifacts/full15/{turns,transcript,chapters}.json` (или перегнать full на том же unified gain).  
2. Нарезать по `cut_plan_15min_3` окна part01/02/03.  
3. Положить в `eval/d5_ttft_split/reference_full15/` (gitignored):  
   - `part0{1,2,3}_{transcript,chapters,turns}.json`  
   - `full_{transcript,chapters,turns}.json`  
   - короткий `README.md`: источник commit/job, «не ручной gold».  
4. Критерии сверки mid-пайплайна (assign+B) vs reference:  
   - text LCS / coverage по part (как glue script);  
   - число крупных спикеров (speech ≳ 30 s) ≥ 3 на полном 15′ после EOS;  
   - mid: не требовать 5 id как full; но **не** схлопывать в 2 на EOS;  
   - выборочный слух hotspot (кабель ~365–375) после EOS ≈ full.  
5. **Gate Phase 0:** reference лежит на диске; скрипт сравнения документирован.

### Phase 1 — Config + audio/VAD orchestration (без UI)

- `file_max_db: 2.0`; unified normalize path для job.  
- Shared speech artifact на job; parts = time slices.  
- Cut plan writer в job dir.  
- **Не** ломать одиночный full-pipeline path (feature flag / `pipeline.ttft_split: true`).

### Phase 2 — Mid diar B + gallery

- Part1 AHC → `centroids.json` / gallery.  
- Part2+ assign + absorb (переиспользовать logic из research `centroid_assign.py`, упрощённо).  
- Сохранять **window embeddings** (+ times) для EOS.  
- Smoke: part1 speakers ⊆ {00,01,…}; part2 может добавить id; на voice_002 mid **допускает** flicker, EOS чинит.

### Phase 3 — ASR / packing / early publish

- ASR per part turns.  
- Packing tail across parts.  
- Early artifact publish after part1 (`until` semantics / job events).  
- LLM batch titles — минимально: не блокировать part1 publish.

### Phase 4 — EOS V1 refine + speaker lock

- AHC(all saved embeddings).  
- Remap → interim ids (Hungarian/greedy by duration).  
- Rewrite turns (+ optional chapter speaker lists).  
- API/UI: `speakers_finalized: false` → lock edit; `true` после EOS.

### Phase 5 — Сверка vs reference_full15

- Прогон demo 15′ с `ttft_split`.  
- Сравнить EOS turns/transcript с reference (LCS, speaker count large, hotspot).  
- Короткий `agent_docs/reports/d5_ttft_split/product_gate.md`.  
- **HUMAN_GATE** на слух + метрики.

---

## Вне scope (бэклог)

- Online H1/V3 cluster-match.  
- Dual centroids / Viterbi / sticky.  
- Jina / packing D.  
- Live partial chapters без absorb (старый mode B pain).  
- Ручной diar gold как gate.

---

## Открытые мелочи (не блокируют старт Phase 0–1)

| Вопрос | Предложение по умолчанию |
|---|---|
| Remap EOS ломает уже показанный текст спикеров в UI? | Меняем только labels; текст ASR не перегоняем, если границы turn’ов совместимы; если turn boundaries сильно съехали — optional re-ASR later (не в MVP). |
| Titles после EOS? | MVP: не пересчитывать, только speaker fields. |
| 2 dB мало на тихой записи? | Логировать `gain_db` + `capped: true`; поднять лимит отдельным тикетом. |
| Сколько parts на 30 мин? | Тот же алгоритм 4–6 мин → N parts. |

---

## Definition of done (продуктовый шип)

- [ ] Flag `ttft_split` гоняет 15′ voice_002 slice end-to-end.  
- [ ] TTFT: первая глава после part1 (замер wall).  
- [ ] Mid = assign+absorb; EOS V1; speakers locked until EOS.  
- [ ] Eval reference from full15 in `eval/d5_ttft_split/`.  
- [ ] EOS ≈ full по крупным спикерам и тексту (glue + выборочный слух).  
- [ ] Отчёт gate; research-гипотезы H1/V2 online закрыты как «не для mid».

---

## Порядок для агента-фиксика

1. Phase 0 — собрать `reference_full15` из имеющегося full15 + cut plan.  
2. Phase 1 — config gain cap + shared VAD/normalize/cut skeleton.  
3. Phase 2 — gallery assign B + persist embeddings.  
4. Phase 3 — wire ASR/packing/early emit.  
5. Phase 4 — EOS V1 + lock flag.  
6. Phase 5 — compare + gate report.

Не коммитить `eval/` (gitignore). Research scripts под `cloud_out/.../scripts/` — только как reference, перенос в `src/` осознанно.

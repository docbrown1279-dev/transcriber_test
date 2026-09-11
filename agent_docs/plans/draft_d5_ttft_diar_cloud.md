# Черновик: D5.TTFT — скорость + диаризация (cloud research)

**Статус:** APPROVED — handoff `cursor/d5-ttft-diar`  
**Ветка:** `cursor/d5-ttft-diar`  
**Опора:** [`ticket_d5_ttft_experiments.md`](ticket_d5_ttft_experiments.md), [`ticket_d5_diarize_speed.md`](ticket_d5_diarize_speed.md), [`draft_ttft_diarize_split.md`](draft_ttft_diarize_split.md), [`ticket_d1_speaker_clusters.md`](ticket_d1_speaker_clusters.md)

---

## Цель (две оси, один этап)

| Ось | Gate (черновик) |
|---|---|
| **TTFT** на 2 vCPU / 8 ГБ, клип ~15′ | первая titled-глава **≤ 5–6 мин** (warm); cold отдельно |
| **Диаризация** | на клипах job `57cc7073…` (≥2 мужчин + женщина) — мужчины **не** в одном жирном id; женщина не в общем пуле; крошки ≲2–3 с не как отдельные люди |

> Уточнение: в тикетах цель **минуты**, не секунды. Полный wall сейчас ~10–11 мин на 15′ @ 2 CPU; 5–6 **секунд** на том же железе нереалистичны без смены каркаса (ASR-first + Jina D — **вне scope**).

---

## Локальные eval-материалы

### A) Новые клипы (job `57cc7073…`, уже нарезаны)

Источник: `var/jobs/57cc70731a374d6789d4464f28f6a174/normalized.wav` (~30 мин).  
Каталог (gitignore `eval/`): `eval/d5_diar/`.

| clip | source range | файл | зачем |
|---|---|---|---|
| clip01 | 890–950 с | `clips/clip01_embeddings_men.wav` | диалог про embeddings/DINO; в hyp много `SPEAKER_00`, куски `SPEAKER_01` — по смыслу ≥2 мужчин |
| clip02 | 1645–1705 с | `clips/clip02_vadim_q.wav` | «че молчите» / вопрос Вадиму; hyp = почти весь `SPEAKER_00` — явный недосплит |
| clip03 | 500–560 с | `clips/clip03_woman_men.wav` | контроль: женщина (`SPEAKER_03` в hyp) + мужчины — не склеить женщину |

Gold (только локально, **не** в `cloud_in/`): шаблоны в `eval/d5_diar/gold/` — дослушать и заполнить `n_speakers` / роли. ASR-текст в gold **не** нужен.

### B) Soft regression из D1 (уже есть)

`eval/d1/transcribe/{test_apartments,test_ninth,test_transformers,test_voice}.json` + wav в `eval/d1/voice/*/…_full.wav`.

Назначение: после смены порога/окон/тюнера — **не** склеить известных спикеров и **не** наплодить ~20 id. Сравнивать unique `speaker` / крупные кластеры vs gold `SPEAKER_A/B/C/D` (permutation-invariant: важен count и разделение, не имена).

Предпочтительные регрессии (несколько спикеров): **`test_apartments`** (A/B/C), **`test_ninth`** (A/B/D). `test_voice` / `test_transformers` — 2 спикера, smoke.

Полевые якоря (из transcript, не gold):

- ~891–928 с: реплики про embeddings / «бутылку» / «тету дину» — чередование голосов.
- ~1648–1705 с: FAISS → «че молчите» → «нет понятно» → «слушай вадим…» — минимум 2 мужских голоса.

Ожидание по встрече целиком: **3 мужчины + 1 женщина**; на коротких клипах цель — **вытянуть ≥2 мужчин** (третий может молчать).

---

## Что проверяем (порядок)

### A. Ленивая загрузка / cold vs warm (H0) — **только локально**

Не в cloud. Обычный агент на локальной копии ветки: warmup lifespan / file-pick + `model_load_sec` vs `pipeline_sec`. Cloud не гоняет H0 и **не** пишет прод-код по полным правилам (дорого по токенам).

### B. Размеры окна WeSpeaker (S1) — быстрый A/B

| preset | window_sec | step_sec |
|---|---|---|
| baseline | 1.5 | 0.75 |
| A | 2.0 | 1.0 |
| B | 3.0 | 1.5 |

Метрики: `n_windows`, wall embed, wall cluster, число **крупных** id (speech ≳ 30 с на полном / ≳ 5 с на 1′ клипе), судьба женщины на clip03 + полном 15′.

### C. Разрез файла + якорь центроидов (S2) — главный рычаг TTFT

Как в `draft_ttft_diarize_split.md`: VAD → cut ~40–60% → part1 diarize+ASR+TOC → ранняя глава; part2 embed + **cluster с якорем** → merge.

Критично: один writer артефактов; remap `SPEAKER_*`; без live partial TOC.

Gate: TTFT ≤ 300–360 с @ 2 CPU warm на 15′.

### D. Тюнер кластеров + крошки (S3 / D1) — качество, кластер дешёвый

Сетка **не** 20 точек. Тюнер прогоняет короткий набор:

1. `cluster_distance_threshold` ∈ {0.80, 0.82, 0.85, 0.88} (или 3 точки вокруг 0.85).
2. Опционально: linkage / metric уже cosine — не трогать без причины.
3. Постфильтр: speech кластера ≲ 2–3 с **на длинных** (>5–10 мин) → приклеить к ближайшему центроиду **или** ближайшему по времени крупному соседу.
4. Метрики сравнения (без DER gold):
   - число крупных кластеров vs ожидаемое `n_speakers` на клипе;
   - «колено» / gap в иерархии linkage distances (если доступно из Agglomerative);
   - доля речи в top-1 кластере (сейчас ~80%+ = FAIL недосплит);
   - женщина отделена на clip03 (бинарный глаз).

Кластеризация мгновенна → гонять тюнер на **клипах** (дешёво) + 1 полный 15′ smoke.

### E. Вне scope

- Jina / packing D / ASR-first.
- pyannote torch на 2 vCPU.
- Live TOC mode B с дырами.
- Gold ASR / пересборка `data/voice_002` transcript.

---

## Cloud vs local

| Где | Что |
|---|---|
| **Cloud** | Только **исследование гипотез**: S1 A/B окон; тюнер порога + crumb; embed vs cluster timings; таблицы в `cloud_out/`. Скрипты/ноутбуки/одноразовый код ок. **Не** полноценный прод-пайплайн, контракты, UI, merge-ready PR. |
| **Local** | H0 warmup; разметка gold; soft regression на `eval/d1/transcribe`; HUMAN_GATE; S2 разрез+якорь и любой продакшен-код обычным агентом на ветке |

В `cloud_in/inputs/`: wav клипы (без gold) + краткий prompt с гипотезами. Без `eval/` целиком, без H0, без «implement production per coder_*.md».

---

## Definition of done (черновик этапа)

- [ ] 2–3 клипа + заполненный human gold (`n_speakers`, роли) в `eval/d5_diar/`.
- [ ] Цифры S1: хотя бы один preset быстрее baseline по diarize wall без склейки женщины.
- [ ] Тюнер: таблица threshold × крупные кластеры / top1 share на клипах; рекомендация порога или «WeSpeaker потолок».
- [ ] S3 crumb rule: прототип или отказ с причиной.
- [ ] S2: спека merge+anchor **или** blocker; код — по go после HUMAN_GATE качества.
- [ ] H0: cold/warm разделены в отчёте.
- [ ] Jina не тащили.

---

## Порядок работ после ✅

1. Дослушать клипы → заполнить `eval/d5_diar/gold/*.md` (человек).
2. Cloud-agent-setup (если env изменился) → pack `cloud_in/` → ветка `cursor/d5-ttft-diar` → push.
3. Cloud: S1 + тюнер + crumb + отчёт.
4. Local ingest → HUMAN_GATE спикеров → спека S2 → Phase B coder (отдельный ✅).

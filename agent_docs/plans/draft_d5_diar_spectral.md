# Черновик: D5.diar2 — spectral / hybrid / timing (cloud research)

**Статус:** APPROVED — handoff  
**Ветка:** `cursor/d5-diar-spectral`  
**Предшественник:** `cursor/d5-ttft-diar` (AHC порог + окна; crumb; вердикт: окна не трогать)

---

## Зачем

1. Один cosine `distance_threshold` хрупкий; хотим **алгоритмы**, не фильтр «<3 с».
2. Найти «одинокого» **SPEAKER_B** (на clip01: «добрый день…» ~42–45 с, без перебивания).
3. На старых кусках тоже был потеряшка: **ninth SPEAKER_A** (~5 с речи), при грубых окнах пропадал и **apartments A**.
4. Замер wall на **~5 мин** (на 60 с порог почти не меняет число операций заметно).
5. Разделить **model_load** vs **embed** (подозрение: на 15′ diarize ~70% wall, на 22′ ~50% — возможен cold load).

**Не делаем:** crumb/duration filter как основной метод; жёсткий prior K∈[2,4]; второй эмбеддер; prod-код.

---

## Методы (один WeSpeaker ResNet34, те же эмбеддинги)

| id | Алгоритм |
|---|---|
| M0 | Baseline AHC cosine average + `distance_threshold` ∈ {0.80, 0.85, 0.88} |
| M1 | **Spectral** clustering на cosine affinity + **eigengap** для K (широкий диапазон, напр. K≤20, без prior 2–4) |
| M2 | **Hybrid:** AHC (M0) → кандидаты смен спикера → локально/вторым проходом spectral (или re-cluster окрестности смены) |
| M3 | Опционально лёгкий **anchor→assign** (опорные окна → cluster → assign rest) — если успеют |

Без post-filter по speech≤3 с. Crumb-статистику можно **логировать**, не применять.

---

## Данные в pack (без gold)

| файл | роль |
|---|---|
| `clips/clip01..03.wav` | качество (локальный gold после ingest) |
| `clips/concat_01_02_03.wav` | 180 с склейка размеченных |
| `clips/timing_5min.wav` | contiguous ~5 мин из того же job (wall) |
| `regression/test_apartments.wav`, `test_ninth.wav` | старые «потеряшки» |

Сравнивать качество **только** на известных окнах (clip01–03, apartments, ninth). Новую разметку не делать. На `timing_5min` — только timings / n_id, не human roles.

---

## Метрики

- Wall: `model_load_sec` (cold 1st process vs warm 2nd), `embed_sec`, `cluster_sec`, `n_windows` на timing_5min и concat.
- Качество (облако без gold): n_id, speech per id, top1 share, timelines.
- Локально после: purity / match vs gold; отдельно — **нашёлся ли B** на clip01 (отдельный id с overlap на «добрый день»).

---

## Вне scope

H0 warmup в прод; S2 split; Jina; pyannote; coder/tester prod ритуал.

---

## DoD

- [ ] Таблица M0/M1/M2 на clip01–03 + apartments/ninth  
- [ ] Timings cold/warm на 5 мин  
- [ ] Вердикт: spectral/hybrid помогает B / потеряшкам или нет  
- [ ] Рекомендация для локального HUMAN_GATE  

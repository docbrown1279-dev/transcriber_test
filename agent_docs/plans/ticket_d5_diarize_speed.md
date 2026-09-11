# Тикет: ускорение / исследование диаризации (WeSpeaker)

**Статус:** CLOSED — окна/spectral/twopass/unit-AHC отработаны; демо **2A**; H0 warmup моделей **REFUSED**  
**TTFT дальше:** [`ticket_d5_ttft_file_split.md`](ticket_d5_ttft_file_split.md)  
**Отчёты:** [`agent_docs/reports/d5_diar/`](../reports/d5_diar/README.md)  
**Связано:** [`draft_ttft_diarize_split.md`](draft_ttft_diarize_split.md), [`ticket_d1_speaker_clusters.md`](ticket_d1_speaker_clusters.md).

---

## Полевые замеры (VPS demo, 2026-09-10)

- **15′ клип → полный прогон ~10:37** wall на удалённом 2 vCPU — терпимо для «дождаться конца», всё ещё тяжело как TTFT (первая глава ≈ конец пайплайна).
- Ориентир по ощущению: **TTFT 5–6 мин** на том же железе реалистичен через **H3 (разрез)** ± H2 (грубее окна), без смены каркаса C.
- Ещё агрессивнее («пара минут» до черновика TOC): **направление B** — diarize в хвост / ASR-first + late chunking **Jina (вариант D)**; см. draft_ttft + блок Jina ниже.

---

## H0 — cold/warm моделей — **REFUSED (2026-09-11)**

Разница load WeSpeaker ≈ секунды; на демо не делаем. Preload **аудио** (не моделей) → [`ticket_d5_ui_upload_progress.md`](ticket_d5_ui_upload_progress.md).

---

## Почему долго в steady-state (не кластеризация)

Код: `src/transcriber/diarization/wespeaker.py`.

1. По всем VAD-островам скользящее окно **`window_sec=1.5`**, шаг **`step_sec=0.75`** → на ~15–25 мин речи **сотни–тысячи** вызовов `SpeakerEmbedder.embed` (WeSpeaker ResNet34 ONNX).
2. **AgglomerativeClustering** по уже посчитанной матрице — обычно **секунды или меньше**; не объясняет 6–9 мин wall.
3. Итог: тормоз = **эмбеддинги × число окон** (CPU ONNX), плюс чтение всего WAV. Кластер — хвост.

Грубая оценка: `speech_sec / step_sec` ≈ число окон (с overlap). Укоротить шаг/окно или речь → почти линейно быстрее.

Замеры D5/полного файла: diarize ~400–540 с при ASR ~200–370 с → diarize часто **главный** вклад в TTFT, пока ASR ждёт полный `turns.json`.

Смена эмбеддера (TitaNet / ERes2Net) в 1f2 **не** давала порядка по скорости на коротких клипах и тот же счётчик спикеров — не первый рычаг для TTFT.

---

## Jina (вариант D) — тяжёлая ли?

Из research 2b ([`docs/research_results/research_plan.md`](../../docs/research_results/research_plan.md), [`reports/2b/`](../../docs/research_results/reports/2b/)):

| | C (demo сейчас) | D (late chunking) |
|---|---|---|
| Модель | `rubert-tiny2` (~десятки М параметров) | `jinaai/jina-embeddings-v3-hf` **~570M**, ctx 8192 |
| Нужна диаризация до TOC? | **да** (packing cross-speaker) | **нет** для границ глав (эмбеддинги текста) |
| Роль diarize | обязательна до chunk | можно **после** (метки спикеров ретро) |

Jina **существенно тяжелее** tiny2 по весам/RAM/CPU encode; официальный flash-чекпоинт в исследовании не встал на transformers 5.16 — брали hf-порт. На 2 vCPU / 8 ГБ: риск по диску+пику RSS рядом с GigaAM torch; не «бесплатный» путь к быстрой TOC.

Имеет смысл для TTFT **только** если сознательно идём в ASR-first + D (направление B в draft_ttft): diarize не блокирует первое оглавление. Иначе для 5–6 мин остаёмся на **C + H3**.

---

## Направления (по приоритету)

| id | Идея | Ожидание | Риск |
|---|---|---|---|
| H0 | Warmup моделей (см. выше) | −cold на первом job | RSS / сложность |
| H1 | **Профилировать** embed wall vs cluster vs I/O vs model_load на 15′ | цифры cold/warm | — |
| H2 | Грубее окна (напр. 2.0 / 1.0 или 3.0 / 1.5) A/B | −30–50% diarize wall? | хуже DER / склейка мужчин |
| H3 | **Разрез файла** + diarize part1 → ранний ASR; part2 с **якорем** центроидов part1 | TTFT ~5–6 мин на 15′ (цель) | стык спикеров; см. draft_ttft |
| H4 | Качество: порог / фильтр крошек / мужские голоса | не скорость | [`ticket_d1_speaker_clusters.md`](ticket_d1_speaker_clusters.md) |
| H5 | Другой движок ради скорости | едва ли ×10; sherpa медленнее в 1f | качество packing C |
| H6 | ASR-first + Jina D, diarize в хвост | черновой TOC за ~пару минут? | тяжёлая Jina; ломает C; отдельный этап |

Порядок величины «в 10 раз» одним только WeSpeaker **маловероятен** без огрубления окон или урезания объёма речи до первой главы (H3).

---

## Цель тикета

1. H0: выбрать warmup (startup vs file-pick) + лог cold/warm.
2. H1: `embed_runtime_sec`, `n_windows`, `cluster_runtime_sec`, `model_load_sec` в `turns`/bench.
3. H2: один A/B на 15′ (качество глазами + wall).
4. Спека H3 согласована с `draft_ttft_diarize_split.md` → coder этап при go (основной рычаг к 5–6 мин).
5. H6 не начинать, пока нет go на смену каркаса C→D / гибрид.

---

## Не делать сразу

- Live partial TOC с незамёрзшими главами (уже обожглись).
- Bakeoff pyannote torch на 2 vCPU «для скорости».
- Тащить Jina в demo «на всякий случай» без спеки B.

# Этап 2b — четыре независимые гипотезы чанкинга

Победителя нет: оценку границ и названий делает человек в локальном `eval/2b_chapter_review.json`. Каталог `eval/` не читался.

Рабочие ветки: `cursor/stage2b-four-hypotheses-4305` (этот прогон) и `cursor/stage1e-four-asr-be20` (те же коммиты). База плана: `cursor/stage2b-chunking`.

## Среда

- CPU: 4 vCPU, RAM: 15 GiB, GPU нет.
- Python `.venv`: `torch 2.13.0+cpu`, `sentence-transformers 6.0.0`, `transformers 5.16.1`, `llama-cpp-python 0.3.35` (как на этапе 2); для D доустановлен `einops 0.8.2` после явного запроса.
- Эмбеддер A/C: `cointegrated/rubert-tiny2`.
- LLM: локальный `Qwen3-8B-Q5_K_M.gguf` (`Qwen/Qwen3-8B-GGUF`), `llama.cpp`, 4 потока. Аудио в модель не подавалось.
- Gemini / NVIDIA: 0 вызовов.
- Аудио, pyannote, GigaAM, Whisper, шумодавы, stage2-скрипты — не запускались. `results/{asr,chunking,llm,reports}/2/` не перезаписывались.

## Неизменный вход

| Листья | Путь | n | Пустые |
|---|---|---:|---|
| A/B | `results/chunking/2/attempt_2_chunks_titled.json` | 63 (id 0–62) | нет |
| C/D | `results/asr/2/gigaam_v3_rnnt/meeting_sample.json` | 183 (id 0–182) | 21, 86, 99, 138 |

Длительность записи 1468,662 с. Максимум длительности листа A/B: 128,4 с (ни один исходный чанк не шире 180 с). Максимум ASR-сегмента: 25 с.

Валидатор: `start`/`end` главы равны `start` первого и `end` последнего source id; ids подряд; покрытие без дыр и перестановки; `timing_method: source_boundaries`. Qwen вызывался только после этой проверки и не менял границы.

Самопроверка валидатора (`scripts/stage2b_selftest.py`): хороший пример принят; сдвиг времени, дыра и перестановка отвергнуты.

## Опыт A — эмбеддинг 63 названий (без LLM-склейки)

Соседний cosine по **title**, `rubert-tiny2`. Капы: ≤8 листьев, ≤180 с. Три порога, отдельный лог на каждый.

| Порог | Глав | Принятых merge | coverage |
|---:|---:|---:|---|
| 0,85 | 63 | 0 | ok |
| 0,80 | 63 | 0 | ok |
| 0,75 | 62 | 1 | ok |

Соседние cosine названий: min 0,352 / med 0,595 / max 0,753. Единственная склейка на 0,75: листья 30–31. Выбран 0,75 как ближайший к 12–18 среди валидных (62 всё ещё далеко от 8–20).

Qwen переименовал только новую группу: «Согласование квартирой и схемы сетей связи». Остальные 61 название этапа 2 оставлены (packing почти не менялся).

**Наблюдение.** Соседние готовые названия для tiny2 — разные темы. Проблема one-shot склейки этапа 2 не сводится к «модель теряет id»: эмбеддинг названий почти ничего не склеивает.

Артефакты: `results/chunking/2b/exp_a_t085.json`, `exp_a_t080.json`, `exp_a_t075.json`, `exp_a_chapters.json`, `review_sheet_a.json`, `merge_log_pass{1,2,3}.json`.

## Опыт B — попарный Qwen (независимо от A)

Ровно одна соседняя пара на вызов. Merge только при валидном `same_topic: true`, совпадении id и капах 8 / 180 с. Иначе `keep`. Два полных прохода.

Первый прогон оборван после 14 пар: модель часто писала невалидный JSON у `title` при `false` (`"title":`, `"title":("")`). Это уже давало `keep`. Парсер укреплён; прогон перезапущен. Черновик: `results/llm/2b/exp_b_pair_decisions_interrupted.json`.

Итоговый прогон: 106 записей лога, из них 102 вызова LLM, wall ~1610 с генерации.

| Проход | Глав после | coverage |
|---|---:|---|
| 1 | 45 | ok |
| 2 | 43 | ok |

Решения: `same_topic` 20, `different_topic` 33, `unparseable` 49 (битый `title` при отказе — трактовались как `keep`), `cap_duration` 4. Максимум листьев в группе: 5. В 8–20 не попали.

Артефакты: `exp_b_chapters.json`, `review_sheet_b.json`, `merge_log_pass{4,5}.json`, `results/llm/2b/exp_b_pair_decisions.json`.

## Опыт C — packing разных спикеров (независимо)

Единица: исходный ASR-сегмент. Пустые строки присоединены к соседу (prev, иначе next) и остались в покрытии. Реплику >~80 слов резали только по уже существующим кускам; внутри сегмента не резали.

Pack: соседний другой спикер при gap ≤2 с; ориентир 40–80 слов. Затем один tiny2 adjacent 0,70, кап длительности 180 с, без капа числа ASR-листьев.

| Шаг | n |
|---|---:|
| Куски (pieces) | 180 |
| Pack-единицы | 37 |
| После tiny2 0,70 | **14** |

14 глав — в предпочтительном диапазоне 12–18. Title-embed второй проход не нужен (уже ≤20). Qwen дал 14 названий ≤10 слов (~216 с). Кап 180 с сработал 4 раза на tiny2-склейке. Максимум главы 177,4 с.

Валидация после заголовков: ok, 183/183.

Артефакты: `exp_c_pack.json`, `exp_c_chapters.json`, `review_sheet_c.json`, `merge_log_pass6.json`, `results/llm/2b/exp_c_titles.json`.

## Опыт D — late chunking

После апрува в этой сессии поставлен `einops 0.8.2`. Официальный `jinaai/jina-embeddings-v3` (custom flash code) не загружается на `transformers 5.16.1` (`all_tied_weights_keys`). Использован нативный порт **той же** модели `jinaai/jina-embeddings-v3-hf` (XLM-RoBERTa ~570M, контекст 8192). Bakeoff других эмбеддеров не делался.

Алгоритм: атом = ASR-сегмент; окна 240 с / overlap 60 с (9 окон); mean-pool token span; cosine соседей, усреднение по окнам; локальные минимумы, главы 45–180 с (цель 75–150).

**12 глав**, все 80,9–144,3 с — в предпочтительном 75–150 и в целевых 8–20. Покрытие 183/183, timing ok. Wall эмбеддинга 13,7 с. Затем 12 заголовков Qwen (~179 с) после валидации.

Не запускались: `Alibaba-NLP/gte-multilingual-base`, `BAAI/bge-m3`, `Qwen/Qwen3-Embedding-0.6B`.

Артефакты: `exp_d_chapters.json`, `exp_d_boundary_scores.json`, `review_sheet_d.json`, `merge_log_pass8.json`, `results/llm/2b/exp_d_titles.json`. Первый отказ: `exp_d_skipped.json`.

## Сводка кандидатов

| Опыт | Глав | В 8–20 | timing_exact (авто) |
|---|---:|---|---|
| A title-embed 0,75 | 62 | нет | ok |
| B pairwise Qwen | 43 | нет | ok |
| C cross-speaker + tiny2 | 14 | да | ok |
| D late chunking (jina-v3-hf) | 12 | да | ok |

`results/chunking/2b/chapters.json` — все кандидаты, `winner_selected: false`. Полный текст в отчёт не копировался.

## Вне скоупа (не делалось)

ASR, диаризация, аудио, шумодавы, повтор этапа 2, четвёртая схема «один спикер», bakeoff эмбеддеров, сравнение LLM, полное саммари, Gemini/NVIDIA, чтение `eval/`.

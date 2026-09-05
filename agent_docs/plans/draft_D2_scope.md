# Черновик этапа D2 — чанкинг и названия глав (Фаза A → B)

**Статус:** INSTRUCTIONS_READY (Phase B prepared). Branch `cursor/demo-d2-chapters`.
**Предшественник:** D1 — Silero T2 в `config/base.yaml`; publishable hyp `data/voice_002/`; backlog GigaAM — не блокер.
**Стратегия:** сначала **повторить** исследование (packing C + `rubert-tiny2` 0,70 + prompt P1), без bakeoff C/D и P1/P2. Улучшения — только после локального human gate, отдельным тикетом.
**Источники:** [`draft_demo_roadmap.md`](draft_demo_roadmap.md) §D2, контракты G2 / `chapters.json`, [`docs/research_results/reports/2b/conclusions.md`](../../docs/research_results/reports/2b/conclusions.md), [`reports/3/notes.md`](../../docs/research_results/reports/3/notes.md).

---

## 1. Цель

Цепочка на готовом транскрипте:

`transcript.json → packing_c (+ rubert_tiny2) → chapters (без title) → Gemini title_p1_v1 → chapters.json`

Артефакт этапа: `chapters.json` (границы + `title` + `source_ids` + metrics).

Не входит: ASR/VAD/диаризация, insights/report (D3), веб (D4), late chunking Jina, гибрид C→D, локальный Qwen в облаке.

---

## 2. Повтор исследования (обязательный каркас)

| Шаг | Как в 2b / 3 | Параметры |
|---|---|---|
| Единица | ASR-сегмент | пустые — к соседу (prev, иначе next); покрытие всех non-empty `source_ids` |
| Pack | разные спикеры, gap ≤2 с | ориентир 40–80 слов на pack-единицу |
| Merge | adjacent cosine `rubert-tiny2` | порог **0,70**; кап длительности **180 с** |
| Таймкоды | копирование | `start` = start первого сегмента, `end` = end последнего |
| Titles | prompt **P1** one-shot | Gemini 2.5 Flash; `title` ≤10 слов, noun phrase; без штампов в начале |
| Не делать | — | bakeoff A/B/D; P2; вторая LLM; правка `transcript.json` |

Ожидание по плотности (ориентир исследования: ~14 глав / ~24,5 мин ≈ 0,57 гл/мин). На новом T2-транскрипте (274 сегмента vs ~183 в research) число глав может отличаться — судит **G2.2**, не «ровно 14».

---

## 3. Что делает облако

1. Preflight: pack (`STACK.md`, `transcript.json`), `GEMINI_API_KEY`, `HF_TOKEN` (скачать tiny2).
2. Реализации: `rubert_tiny2` embedder, `packing_c` chunker, `gemini` client, prompt file `title_p1_v1`, pipeline steps `chunk` + `titles`, G2 quality helpers.
3. Прогон на packed `cloud_in/inputs/artifacts/voice_002/transcript.json` (без аудио).
4. `cloud_out/artifacts/voice_002/chapters.json` + `gate_D2.md` + `run_meta.json`.
5. pytest / ruff / mypy / bandit; push ветки (без PR).

---

## 4. Автопроверки (G2)

| id | Суть |
|---|---|
| G2.0 | Preflight pack + secrets |
| G2.1 | времена глав = границы сегментов |
| G2.2 | `chapters_per_minute` ∈ [0.4, 0.8] pass; [0.3, 1.0] WARN; иначе FAIL |
| G2.3 | главы &lt;45 с / &gt;180 с — список, WARN |
| G2.4 | title ≤10 слов |
| G2.5 | title не начинается со штампа |
| G2.6 | titles unique, non-empty |
| G2.7 | `source_ids` покрывают каждый non-empty segment ровно раз |
| G2.8 | agent judgement hit/generic/miss; `miss ≤ 1` на 12–14 глав |

Штампы (начало title, case-insensitive): `обсуждение`, `обсудили`, `говорили о`, `совещание по`, `разговор о`.

---

## 5. Ручной шлюз (локально, после облака)

1. Ingest `chapters.json` → `results/d2/` или `agent_docs/reports/D2/`.
2. Человек читает оглавление на полной записи (`data/voice_002/transcript.md` + аудио).
3. Решение: принять как есть **или** открыть тикет на улучшение (порог / pack / prompt id) — **не** в том же cloud run.
4. `HUMAN_GATE: PASS|FAIL` в `stage_D2.md`.

---

## 6. Зависимости (нужно ✅ пользователя)

| Пакет | Зачем |
|---|---|
| `sentence-transformers` (или `transformers` + согласованный torch CPU) | `cointegrated/rubert-tiny2` |
| `google-genai` (или актуальный официальный Gemini SDK) | Gemini 2.5 Flash |

Секреты: `GEMINI_API_KEY` (обязателен для titles), `HF_TOKEN` (скачивание tiny2). Аудио в API не отправляется.

Конфиг: при отсутствии ключей добавить в `chunking` (без магических чисел в коде):

- `packing_target_words: [40, 80]`
- `merge_max_duration_sec: 180` (или читать верх из `target_chapter_sec`)

---

## 7. Pack `cloud_in/`

| Класть | Не класть |
|---|---|
| `inputs/STACK.md` (обновить при необходимости) | `inputs/audio/*` (D1) |
| `inputs/artifacts/voice_002/transcript.json` (копия из `data/voice_002/`) | `baseline_*.json`, gold, `eval/` |
| `prompt.md`, `HANDOFF.md` | полный job `var/jobs/…` |
| `agent/` роль (стабильная) | |

Вход облака — **только текст**. ASR не пересчитывать.

---

## 8. Улучшения (после human gate, не в D2 v1)

Кандидаты только если оглавление «не ориентир»:

- порог similarity / кап 180 с / target words;
- новый `prompt_id` (не правка `title_p1_v1` in-place);
- опционально late chunking D как stub уже есть — bakeoff только по явному тикету.

---

## 9. Done criteria

- [ ] Код packing C + rubert + Gemini titles по контрактам
- [ ] `chapters.json` на packed T2 transcript
- [ ] `gate_D2.md` G2.0–G2.8 без ослабления порогов
- [ ] Ветка запушена; PR — локальный `cloud_pr.sh` после ingest
- [ ] Локальный HUMAN_GATE записан

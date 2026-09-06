# Черновик этапа D3 — инсайты и отчёт LLM (Фаза A)

**Статус:** INSTRUCTIONS_READY (Phase B). Branch `cursor/demo-d3-insights`.
**Предшественник:** D2 HUMAN_GATE PASS (packing C + P1, absorb &lt;5 с, 14 глав).
**Стратегия:** повторить исследование 3c (extract по главам → один report). LLM — [`draft_llm_wrapper.md`](draft_llm_wrapper.md): `mode: api`, backend по умолчанию Gemini; NVIDIA/Qwen — API, не локальный GGUF.
**Источники:** [`draft_demo_roadmap.md`](draft_demo_roadmap.md) §D3, контракты G3, [`docs/research_results/reports/3c/notes.md`](../../docs/research_results/reports/3c/notes.md).

---

## 1. Цель

```
transcript.json + chapters.json
  → meeting_insights/v1_extract (1 вызов / глава) → insights.json
  → meeting_insights/v1_report (1 вызов на merge) → report.json
  → markdown export (без LLM)                     → report.md
```

Не входит: ASR/VAD/диаризация/чанкинг, веб (D4), правка транскрипта, late chunking, P2, **локальный llama.cpp**, подгонка фильтра «нет инсайтов».

---

## 2. Каркас 3c

| Шаг | Как в 3c | Параметры |
|---|---|---|
| Вход | главы C + ASR-текст | packed `voice_002`, 14 глав |
| Extract / report | API, текст | пути из `config/base_llm.yaml`; demo `backend: gemini` |
| Таймкоды | копирование | модель даёт `segment_id` |
| Спикеры | детерминированно | `label: null` |
| `report.md` | рендер JSON | не второй ответ модели |
| Черновик | всегда | `draft_warning: true` в demo |

Пустые `key_points` у коротких глав допустимы.

---

## 3. Данные

Локально: `data/voice_002/{transcript.json,transcript.md,chapters.json}` (главы из `results/d2_cloud/`, покрытие 267 nonempty, missing/dup = 0).

Pack после ✅: `cloud_in/inputs/artifacts/voice_002/{transcript.json,chapters.json}` + `STACK.md`. Без аудио, `eval/`, GGUF.

---

## 4. Что делает облако

1. Preflight: pack + ключ **активного** backend (по умолчанию `GEMINI_API_KEY`).
2. Обёртка: `config/base_llm.yaml`, промпты/схемы из контракта, обобщённый Gemini, **рабочий** `openai_compat` (NVIDIA/Qwen). `local_llama` не трогать.
3. Extract + report + clock-gate + markdown; `requires` включает `transcript.json`.
4. Прогон выбранным backend на 14 главах → `cloud_out/artifacts/voice_002/{insights.json,report.json,report.md}`.
5. G3.0–G3.9, lint, push ветки (без PR).

Бюджет: `max_calls_per_job: 40`. Превышение — FAIL.

---

## 5. G3

Как в [`quality_gates.md`](../contracts/quality_gates.md): G3.0 требует имя env из `backends[backend].api_key_env`, не хардкод Gemini.

---

## 6. Ручной шлюз

Читать `report.md` на полной записи. Смена модели — `llm.backend` в yaml, тот же промпт. `HUMAN_GATE` в `stage_D3.md`. Новый промпт = новый файл версии.

---

## 7. Зависимости

| Пакет | Зачем |
|---|---|
| `google-genai` | уже есть, Gemini |
| `httpx` | extra `llm` — NVIDIA/Qwen OpenAI-compat |

Не ставим `llama-cpp-python`. Не качаем GGUF. OpenAI-compat transport: **`httpx`** in extra `llm`.

---

## 8. Контрактные правки

- `insights_extract.requires = (chapters.json, transcript.json)`
- hydration `segment_id` → часы
- схемы в `llm/schemas/`, путь в yaml
- Q3 уточнён: облако = API; ключи Gemini/NVIDIA/Qwen — имена env

Примеры: [`../contracts/llm/`](../contracts/llm/).

---

## 9. Done criteria

- [ ] `base_llm.yaml` + extra + prompts/schemas в пакете
- [ ] Extract + report + markdown на packed voice_002 (Gemini)
- [ ] `openai_compat` живой (NVIDIA/Qwen конфигом, без обязательного живого вызова в шлюзе)
- [ ] `local_llama` по-прежнему заглушка
- [ ] G3 без ослабления порогов; ветка запушена; HUMAN_GATE

---

## 10. Чеклист ✅

1. `mode: api`, `backend: gemini` по умолчанию; nvidia/qwen — API по имени ключа — ок?
2. Один `config/base_llm.yaml`, extra только ссылкой — ок?
3. Схемы в отдельной папке, путь в шаге таски; extra_config только у backend — ок?
4. Промпты по таскам: `chapter_titles`, затем `meeting_insights` (extract + report) — ок?
5. Локальный режим на D3 **не** делаем — ок?
6. Клиент NVIDIA/Qwen: **`httpx`** in extra `llm` (locked for this pack).

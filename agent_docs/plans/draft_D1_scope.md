# Черновик этапа D1 — голос → транскрипт (Фаза A)

**Статус:** INSTRUCTIONS_READY (Phase B). Branch `cursor/demo-d1-speech`.
**Предшественник:** D0 — gate PASS, merge PR #16 в `main`.
**После облака D1:** только **ручной шлюз человека** (не D2). D2 стартует после `HUMAN_GATE: PASS`.
**Источники:** [`draft_demo_roadmap.md`](draft_demo_roadmap.md) §D1, контракты, [`STACK.md`](../../cloud_in/inputs/STACK.md).

---

## Нумерация: D* vs G*

| Буква | Что это | Примеры |
|---|---|---|
| **D0…D5** | **этапы разработки** по roadmap (один этап = один PR) | D0 каркас → D1 речь → D2 главы → … |
| **G0…G5** | **автошлюз** (набор проверок) **внутри** того же этапа | G0 = проверки этапа D0; **G1 = проверки этапа D1** |

G1 — не отдельный шаг между D0 и D1. Это имя чеклиста «прошёл ли D1 в облаке» (`gate_D1.md`: нет латиницы, ru-ratio, схема, …).

Поток:

```text
D0 → D1 (код + полный ASR в облаке + автопроверки G1) → человек локально → merge → D2 → …
```

---

## 1. Где мы сейчас

| Этап | Облако | Код в `main` | Дальше |
|---|---|---|---|
| D0 | PASS | да (PR #16) | закрыт |
| **D1** | ещё нет | нет | после облака — человек |
| D2…D5 | — | — | после HUMAN_GATE D1 |

---

## 2. Цель D1

Цепочка до транскрипта (`demo`):

`normalize → vad → diarize (+ merge) → asr → correction_suggest`

Артефакты: `audio.json`, `speech.json`, `turns.json`, `transcript.json`, `quality.json`, `suggestions.json` (пустой словарь, `applied: false`).

Не входит: чанкинг, LLM, веб-загрузка, Docker.

---

## 3. Что делает облако (подтверждено)

1. Preflight + deps + модели (`HF_TOKEN`).
2. Реализации портов (ffmpeg/gain, Silero, WeSpeaker, GigaAM в подпроцессе, пустой `dictionary_suggest`).
3. **Полный текстовый прогон** на `cloud_in/inputs/audio/voice_002.m4a` (~24,5 мин) → артефакты в `cloud_out/artifacts/voice_002/` (как минимум `transcript.json` + `quality.json`; остальные стадии той же цепочки — рядом).
4. Короткий клип `test_voice.m4a` — для быстрых интеграционных/unit путей по желанию; **основной результат этапа — полный транскрипт**.
5. Автопроверки этапа (G1): pytest + нет латиницы + ru-ratio ≥ 0,90 + валидность схем + отчёт → `cloud_out/gate_D1.md`, `run_meta.json`.
6. Push ветки `cursor/demo-d1-speech` (PR — локальный `cloud_pr.sh`).

Золото `eval/` в облаке **не** читается.

---

## 4. Автопроверки этапа D1 (имя в контракте: G1)

| id | Суть |
|---|---|
| G1.0 | Preflight: pack + `HF_TOKEN` |
| G1.1 | доля русских слов ≥ 0,90 **на полном** `transcript.json` |
| G1.2 | латиница в сегментах = 0 |
| G1.3 | схемы `transcript` / `quality` валидны |
| G1.4 | времена монотонны, внутри длительности |
| G1.5 | дыры и пустые сегменты перечислены |
| G1.6 | wall time + peak RSS (полный прогон) |
| G1.7 | агент: 3–5 фрагментов — связная русская речь |

---

## 5. Ручной шлюз (после скачивания)

1. `/cloud_pull` / ingest: код + `cloud_out` → `agent_docs/reports/D1/` + артефакты полного прогона.
2. Человек слушает 2–3 участка полной записи, сверяет с облачным `transcript.json`.
3. Опционально WER/CER vs `eval/` (локально).
4. `HUMAN_GATE: PASS|FAIL` в `stage_D1.md` → merge или повтор D1.

---

## 6. Зависимости (нужно ✅)

| Пакет | Зачем |
|---|---|
| `onnxruntime`, `soundfile`, `scikit-learn` | Silero + WeSpeaker |
| `torch` + `torchaudio` (CPU) | GigaAM runtime |
| `gigaam` из git `salute-developers/GigaAM` | ASR `v3_rnnt` |
| WeSpeaker / Silero ONNX weights | диаризация / VAD |

Секрет: `HF_TOKEN`. Gemini для D1 не нужен.

---

## 7. Pack

| Файл | Роль |
|---|---|
| `inputs/audio/voice_002.m4a` (~23 MiB) | **основной** вход полного ASR |
| `inputs/audio/test_voice.m4a` | короткий клип для быстрых тестов |
| `STACK.md`, `HANDOFF`, `prompt` | этап D1 |

Не класть: `eval/`, `.env`, `docs/research_results/`.

---

## 7b. Словарь в demo

Порт + `suggestions.json` с **пустым** словарём; транскрипт не правится. Отдельного «словарного» gate нет.

---

## 8. Решения — ✅ (2026-09-05)

1. Scope: полный ASR в облаке → автопроверки → человек локально → D2 — **ок**
2. Deps §6 — **ок**
3. Ветка `cursor/demo-d1-speech` — **ок**

Phase B done: `coder_D1.md`, `tester_D1.md`, pack, handoff push.

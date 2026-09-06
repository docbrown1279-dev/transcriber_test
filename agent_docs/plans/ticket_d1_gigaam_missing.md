# Тикет: D1 — пропавшие куски / тюнинг GigaAM

**Статус:** OPEN (backlog)  
**Ветка:** от свежего `main` → `cursor/d1-gigaam-missing` (когда откроем)  
**Приоритет:** после закрытия Silero parity; **не** блокирует D2 chunking, если human gate ок с текущей читаемостью.

---

## Контекст

Silero parity закрыт (`agent_docs/plans/archived/ticket_d1_silero_parity.md`):

- VAD = snakers4 + context; T2 читаемость на 4 gold ок (`eval/d1/5/`, window recall ~0.73–0.89).
- Текст в целом **осмысленный**; `missing_hyp=0` не значит «весь gold смысл на месте» (pad ±2 с).
- Опечатки вроде **«касторография»** → чинятся **словарём** (correction suggest), не этим тикетом.

Главная боль дальше: **пропавшие / обрезанные куски смысла** (хвосты реплик, письмо/коллектор на `test_voice` 74–83 с, отдельные фразы), а не крошки VAD.

---

## Гипотезы (проверять по порядку)

| id | слой | идея |
|---|---|---|
| H1 | ASR extract / gain | тихий хвост не дотягивает; посмотреть RMS/gain на missing windows |
| H2 | `max_segment_seconds` / split | обрезка длинного turn режет смысл на стыке |
| H3 | GigaAM decode | пустые / короткие сегменты при живой речи — retry / beam / другой checkpoint? |
| H4 | VAD/merge residual | только если H1–H3 не объясняют; не крутить Silero «ещё чувствительнее» без пруфа |

Не открывать заново dynaudnorm C3 как default без сравнения с T2.

---

## План (когда возьмём)

1. Список пропаж с `eval/d1/5/` + human note (что важно для демо).
2. На 3–5 окнах: audio extract + GigaAM-only vs полный пайплайн.
3. 1–2 мягких фикса (gain / split / skip-empty retry) — не сетка 20 вариантов.
4. Повтор diff attempt 6; критерий — читаемость narrative, не WER.

Словарь domain (`касторография` → `квартирография` и т.п.) — отдельный маленький тикет/PR на correction, можно параллельно.

---

## Не делать здесь

- Полный bakeoff pyannote/sherpa ONNX
- Whisper как замена GigaAM
- Возврат C3 по cover% без чтения текста

## Артефакты

- Этот тикет  
- Отчёт: `agent_docs/reports/d1_gigaam_missing.md` (когда будет)  
- Append в `agent_docs/progress/stage_D1.md`

# Тикет: D1 — связность ASR (дробление / обрывки фраз)

**Статус:** READY TO OPEN  
**Ветка:** от `main` → `cursor/d1-asr-coherence`  
  (старая `cursor/d1-silero-tune` уже смержена в PR #18; remote ещё может висеть — не продолжать её, брать свежий main)  
**Контекст:** после dual-path (`vad_input` dynaudnorm + per-turn gain) дыры почти закрыты, но текст часто рваный. Читать: `results/d1_dual/transcript.md`.  
**Eval:** `eval/d1/4/transcript_diff.md` (pad ±2s).

---

## Симптом

В полной расшифровке много коротких сегментов и обрывков («связь», «правильные», «определено точ»), по которым нельзя восстановить смысл. Покрытие речи хорошее; **связность плохая**.

### Цифры с `results/d1_dual/`

| слой | n | median dur | доля &lt;1s / &lt;2s |
|---|---:|---:|---|
| Silero regions | **689** | **0.8 s** | 411 &lt;1s |
| turns (после merge) | 347 | 2.0 s | 170 &lt;2s |
| ASR nonempty | 339 | 2.0 s | 166 &lt;2s; **132** с ≤3 словами |

`asr.max_segment_seconds=25` почти не режет: сегменты ASR ≈ turns. **Дробление рождается до GigaAM.**

---

## Гипотезы (куда смотреть)

| # | Модуль | Почему похоже | Что проверить / крутить |
|---|---|---|---|
| **H1** | **VAD + premerge** (главный подозреваемый) | dynaudnorm дал много крошек 0.3–1s; `vad_premerge_gap_sec=0.3`, `min_speech_ms=200` | Увеличить `vad_premerge_gap_sec` (0.5–1.0), `min_speech_ms` (300–500), возможно `min_silence_ms`; A/B C1 vs C3 preprocess |
| **H2** | **Turn merge** | `absorb_turn_shorter_than_sec=1.0`, `same_speaker_gap_sec=0.3` — короткие turns не склеиваются в фразы | Поднять absorb до 1.5–2.5s, gap до 0.5–0.8s (осторожно со сменой спикера) |
| **H3** | **Per-turn gain → GigaAM** | Gain на очень коротком куске + пик → мало полезного сигнала / артефакты | Поднять `gain.target_dbfs` / `max_db` **только на slice**; floor минимальной длины slice перед ASR (pad/skip &lt;0.5–0.8s) |
| **H4** | **GigaAM knobs** | Сейчас почти нет тюнимых параметров (`v3_rnnt`, max 25s) | Смотреть API gigaam (beam/temp если есть); иначе вторично после H1–H3 |
| **H5** | **Пост-склейка текста** | Не чинит аудио, но может склеить соседние сегменты одного спикера для UI/чанкинга | Отдельный шаг merge transcript по gap≤X; не путать с правкой границ ASR |

**Вывод для старта:** сначала **H1+H2** (нарезка), потом **H3** (gain/длина куска), **H4** только если связные куски всё ещё дают мусор.

---

## План работы (в новой ветке)

### 0. Ветка

```bash
git checkout main && git pull
git checkout -b cursor/d1-asr-coherence
```

### 1. Диагностика нарезки (без полного ASR)

На `results/d1_dual/` или коротких окнах `eval/d1/partial_windows_dual/`:

- гистограммы длительностей: VAD regions → turns → ASR;
- сколько регионов &lt;0.5 / &lt;1 / &lt;2 s до и после смены merge/premerge.

Скрипт: можно расширить одноразовый stats или `scripts/` helper.

### 2. A/B нарезки (те же 5 rescue + 5 regression окон)

Варианты (не больше 3–4 за проход):

| id | Изменение |
|---|---|
| N0 | baseline dual-path (как сейчас) |
| N1 | `vad_premerge_gap_sec=0.8`, `min_speech_ms=400` |
| N2 | N1 + `absorb=2.0`, `same_speaker_gap=0.6` |
| N3 | N2 + мягче VAD preprocess (`C1` acompressor вместо dynaudnorm) |

Метрики на глаз + счётчики: median turn dur, % сегментов ≤3 слов, читаемость hyp vs gold в `eval/d1/4` style.

### 3. Gain перед GigaAM (per-slice)

Уже есть `asr_per_turn_gain` + `audio.gain.*` на каждый slice в `gigaam.py`.

Попробовать:

- `target_dbfs`: −23 → −20 / −18;
- `max_db`: 18 → 24 (с peak ceiling);
- не гнать ASR на slice &lt; `min_asr_sec` (новый ключ, напр. 0.6): pad из `normalized.wav` или merge в соседа **до** вызова модели.

Сравнивать только на окнах, где нарезка уже улучшена (иначе снова кормим модель крошками).

### 4. GigaAM

- Проверить, есть ли у `gigaam` decode-параметры сверх `transcribe(path)`.
- Если нет — зафиксировать в отчёте «рычагов нет» и не тратить цикл.

### 5. Приёмка

- Rescue/regression окна: меньше обрывков, фразы читаются целиком (human).
- Полный `voice_002` (или 5–10 мин срез): median segment ≥ ~4–6 s или заметно меньше доли ≤3 слов; без взрыва спикеров.
- Eval attempt N: `missing_hyp` не откатывается к уровню attempt 3.

### 6. Не делать в этом тикете

- Новый ASR-движок (Whisper).
- Включать компрессор в `normalized.wav` для ASR.
- Полный bakeoff LLM/чанкинга.

---

## Артефакты

- План/прогресс: этот файл + append в `agent_docs/progress/stage_D1.md`
- Отчёт A/B: `agent_docs/reports/d1_asr_coherence.md`
- Hyp: `results/d1_coherence/` (не затирать `d1_dual` без копии)

## Prompt для отдельного окна (вставить)

```text
Тикет: agent_docs/plans/ticket_d1_asr_coherence.md
Ветка от main: cursor/d1-asr-coherence
Симптом: results/d1_dual/transcript.md — слишком мелкие обрывки.
Сначала H1+H2 (VAD premerge / turn merge), потом H3 (per-slice gain + min length), H4 GigaAM только если останется мусор на длинных кусках.
Не трогать dual-path идею (компрессия только vad_input). Eval окна как в eval/d1/partial_windows_dual и eval/d1/4.
```

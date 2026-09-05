# Тикет: D1 — parity с исследованием 1f (Silero без компрессора) + альтернативы

**Статус:** READY TO OPEN  
**Ветка:** от свежего `main` → `cursor/d1-silero-parity`  
  (не продолжать `cursor/d1-asr-coherence` / не копить тюны на main; remote `d1-silero-tune` — другая история, не брать)  
**Зачем:** текущий demo-текст (`data/voice_002`, C3 dynaudnorm + merge agg) сильно хуже и Stage 2 (pyannote), и **1f Silero на сыром клипе**. Нужно сначала **повторить 1f**, потом слегка улучшить, потом осознанно глянуть альтернативы из отчётов — не маскировать крошки компрессией всего файла.

---

## Контекст (прочитать до кода)

| артефакт | что это |
|---|---|
| `docs/research_results/reports/1f/notes.md` | что гоняли; sherpa vs vad_wespeaker |
| `docs/research_results/reports/1f2/asr_notes.md` | цитаты текста Silero/TEN/FSMN на `test_voice` |
| `docs/research_results/reports/1f2/conclusions.md` | выбранный стек демки |
| `data/research_asr_1f_vad_wespeaker/test_voice.json` | **эталон текста 1f** (восстановлен из git `3569c4e`) |
| `data/research_asr_stage2/transcript.md` | потолок качества = **другой** стек (pyannote 3.1 torch + GigaAM) |
| `agent_docs/reports/d1_75s_stack_compare.md` | сверка gold / stage2 / 1f / current на 0–75 с |
| `eval/d1/3/transcript_diff.md` | D1 attempt 3: много `missing_hyp` (дыры), не «каша от компрессора»; ~26 спикеров чинили отдельно |

### Важная развилка стеков

- **Stage 2 / `full_asr.md`:** pyannote **3.1 + torch** сам сегментирует речь + спикеры. Тексты связные, но дыра 0–10 с на `test_voice`. Это **не** цель parity.
- **1f `vad_wespeaker`:** raw m4a → **Silero ONNX (без dynaudnorm / loudnorm)** → WeSpeaker → merge gap≤0.3 / absorb&lt;1 → linear gain на extract → GigaAM. Текст уже мельче pyannote, но читаемее текущего demo на том же клипе.
- **D1 сейчас:** dual-path + **dynaudnorm на весь `vad_input`** + merge agg → покрытие дыр выросло, связность упала («определено точ», склейка спикеров).

Итог: «в исследовании Silero был лучше» = сравнение с **1f без компрессора**, не с Stage 2.

---

## Цель

1. **Повторить** результат 1f Silero на тех же 4 клипах (минимум `test_voice`), bit-close по смыслу к `data/research_asr_1f_vad_wespeaker/` (не обязаны байт-в-байт JSON).
2. **Подкинуть** 2–3 мягких тюна (не dynaudnorm на весь файл): peak-limit / min_silence / premerge — смотреть **читаемость** канализации+экспертизы на 0–75 с, не только cover%.
3. **Альтернативы из отчётов** — таблица «что пробовали / почему отложили / что ещё не пробовали»; опционально один честный smoke, если легко поднять.

---

## Что пробовали в исследовании (не выдумывать заново)

| id | Что | Вердикт 1f/1f2 |
|---|---|---|
| `pyannote31` torch | полный пайплайн 3.1 | потолок; тяжёлый для демки 2 vCPU |
| `sherpa_onnx` | **pyannote segmentation 3.0 ONNX** + 3D-Speaker ERes2Net + cluster в sherpa | IoU речи ~0.94 (почти как 3.1), но **5–8 спикеров** при `cluster_threshold=0.5`; порог **не** крутили |
| `vad_wespeaker` | Silero VAD ONNX + WeSpeaker ResNet34 | выбран для демки по числу спикеров / скорости; IoU слабее |
| 1f2 VAD | Silero / TEN / FSMN | TEN лучше хвост `test_voice`; FSMN запасной; Silero основной |
| 1f2 embed | WeSpeaker / ERes2Net / TitaNet | одинаковый счётчик спикеров на 4 клипах |

### pyannote-onnx / extended / embedding-onnx?

В 1f **не** гоняли отдельные продукты с именами `pyannote-onnx-extended` / `pyannote-embedding-onnx` как полноценные пайплайны.

Что было:

- **segmentation 3.0 ONNX** — да, как часть **sherpa** (не standalone «pyannote-onnx»).
- **pyannote 3.1 full** — только torch-эталон (и Stage 2 полный файл).
- **community-1** — мелькал в **1b** с Whisper (другой этап), не как ONNX-замена 3.1 в 1f.

GPU-only варианты в 1f не сравнивались (хост без GPU). Если агент находит готовый CPU ONNX community/extended — зафиксировать в отчёте «не пробовали в 1f», не объявлять победителем без замера на 4 клипах.

**Почему sherpa отложили:** не границы речи, а **дрожь спикеров** (packing C нужен стабильный id). Кандидат после nudge `cluster_threshold` — отдельный эксперимент, не блокирует parity Silero.

---

## План работы

### 0. Ветка

```bash
git checkout main && git pull
git checkout -b cursor/d1-silero-parity
```

Не мержить в main без явного ОК человека. Не затирать `data/voice_002/` / `data/research_asr_*` без копии.

### 1. Baseline parity (обязательно)

Конфиг как в 1f (через overlay / временный profile / явные overrides — не ломать `base.yaml` на main до апрува):

- `audio.vad_preprocess.enabled: false` (или нет фильтра) — **сырой** 16 kHz в Silero  
- merge: `vad_premerge_gap_sec=0.3`, `same_speaker_gap_sec=0.3`, `absorb_turn_shorter_than_sec=1.0`  
- `vad.min_speech_ms=200`, `min_silence_ms=200`, threshold 0.5 / neg 0.35  
- ASR: GigaAM v3 + per-extract/per-turn linear gain как сейчас (как 1f)  
- Клипы: `data/test_voice.m4a` (+ желательно apartments/transformers/ninth)

Выход: `results/d1_parity_1f/` (или `eval/d1/partial_parity_1f/`).

Приёмка шага 1:

- на `test_voice` 0–75 с текст **ближе к** `data/research_asr_1f_vad_wespeaker/test_voice.json`, чем к `data/voice_002/`  
- есть «точки подключения» / кусок про экспертизу без «определено точ»  
- в отчёте side-by-side 3 колонки: 1f recovered | parity run | current voice_002  

Если parity не сходится — **стоп**, писать diff настроек/кода (premerge до embed? chunk size Silero? sample rate?), не переходить к компрессору.

### 2. Мягкий тюнинг (после parity)

Не больше 3 вариантов за проход:

| id | идея |
|---|---|
| T0 | parity baseline |
| T1 | peak-only: `alimiter` / `acompressor` с высоким thr **только** чтобы пик ≤ −1 dBFS, без dynaudnorm на весь файл |
| T2 | `min_silence_ms` 300–400 и/или `vad_premerge_gap` 0.5 (merge всё ещё не agg) |

Метрики: human read 0–75 с (канализация+экспертиза); cover на rescue-окнах из `scripts/tune_silero_vad.py` — вторично.  
**Не** возвращать C3 dynaudnorm как default, пока T1/T2 не сравнены с T0 по читаемости.

### 3. Альтернативы (обзор + опциональный smoke)

В отчёте таблица:

1. sherpa + nudge cluster_threshold (0.6–0.8?) на 4 клипах — только счётчик спикеров + IoU; ASR optional  
2. зафиксировать: standalone pyannote-onnx-extended / embedding-onnx в 1f **не** тестировались  
3. TEN/FSMN fallback в дырах — уже в conclusions; не блокирует parity  

Полный bakeoff новых ONNX-пайплайнов — только если человек апрувит отдельным абзацем (бюджет CPU/HF).

### 4. Не делать в этом тикете

- Снова объявлять dynaudnorm C3 победителем по cover% без чтения текста  
- Пересчёт полного Stage 2 pyannote на всём `voice_002`  
- Merge agg (0.8/2.5) как «фикс» крошек  
- Whisper / новый ASR движок  
- Коммит в main без апрува  

---

## Артефакты

- Этот тикет  
- Отчёт: `agent_docs/reports/d1_silero_parity.md`  
- Hyp: `results/d1_parity_1f/` (+ optional `results/d1_parity_tune/`)  
- Append в `agent_docs/progress/stage_D1.md`  

## Prompt для отдельного окна

```text
Тикет: agent_docs/plans/ticket_d1_silero_parity.md
Ветка от main: cursor/d1-silero-parity
Сначала воспроизвести 1f Silero БЕЗ dynaudnorm на 4 клипах (эталон data/research_asr_1f_vad_wespeaker/).
Потом 2–3 мягких тюна (peak-limit / min_silence), не C3 на весь файл.
Альтернативы: сверка с 1f notes (sherpa = seg 3.0 ONNX + over-cluster; pyannote-onnx-extended в 1f не гоняли).
Читать agent_docs/reports/d1_75s_stack_compare.md. Не мержить в main без апрува.
```

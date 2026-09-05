# План исследования (3c закрыт; дальше — словарь и prod-эксперименты)

Указатель отчётов: [`results/reports/notes.md`](../results/reports/notes.md).  
Итог этапов 2+2b: [`results/reports/2b/conclusions.md`](../results/reports/2b/conclusions.md).  
Итог этапа 3: [`results/reports/3/notes.md`](../results/reports/3/notes.md).

Архив 1f+1f2: `cursor/stage1f-onnx-diarization`. Итог: [`results/reports/1f2/conclusions.md`](../results/reports/1f2/conclusions.md).

**Eval-клипы:** [`docs/eval_clips.md`](eval_clips.md). Золото `eval/` агентам не отдавать.

## Карта этапов

| Этап | Статус | Что |
|---|---|---|
| 1e | закрыт | выбор ASR на 4 eval-клипах |
| 2 | закрыт | полный файл GigaAM v3 + pyannote + linear gain; tiny2 «один спикер» не дал 8–20 глав |
| 2b | закрыт | четыре гипотезы чанкинга; **рабочие C и D** |
| 3 | закрыт | Qwen3-8B: P1 one-shot vs P2 two-pass на D; на C ушёл P1 (лучше title, не эталон инсайтов) |
| **1f** | закрыт | ONNX-диаризация: vad_wespeaker (Silero+WeSpeaker) vs sherpa; эталон pyannote 3.1 |
| **1f2** | закрыт | 3 VAD + 3 эмбеддера; Silero + fallback в дырах (TEN или FSMN), WeSpeaker |
| **1f2b** | закрыт | GigaAM v3 на масках TEN и FSMN (хвост `test_voice`) |
| шумодавы | **пропуск** | 1a afftdn резал речь; 1b DeepFilterNet / RNNoise бесполезны |
| **3b** | закрыт | инсайты D + `report.md` (Gemini); локальный assemble тех же инсайтов; API self-check сломан — [`3b/notes.md`](../results/reports/3b/notes.md) |
| **3c** | закрыт | фильтр инсайтов D; Gemini + Qwen независимо; бар промптом не настроен — [`3c/notes.md`](../results/reports/3c/notes.md) |
| словарь | потом | после ASR предлагать замены терминов, не молча править |

Промпт 1f (закрыт): [`docs/prompts/stage1f_diarization.md`](prompts/stage1f_diarization.md).  
Промпт 1f2 (закрыт): [`docs/prompts/stage1f2_vad.md`](prompts/stage1f2_vad.md).  
Промпт 1f2b (закрыт): [`docs/prompts/stage1f2_asr.md`](prompts/stage1f2_asr.md).  
Итог 1f2: [`results/reports/1f2/conclusions.md`](../results/reports/1f2/conclusions.md).  
Промпт 3b (архив): [`docs/prompts/stage3b.md`](prompts/stage3b.md).  
Промпт 3c: [`docs/prompts/stage3c.md`](prompts/stage3c.md).  
Эталон меток 1e (в git): [`results/reports/1f/baseline/pyannote31/`](../results/reports/1f/baseline/pyannote31/).

---

## Зафиксированный стек (не пересматривать без явной просьбы)

**ASR.** GigaAM `v3_rnnt` + linear `volume=` если RMS &lt; −30 dBFS. Torch нужен как рантайм GigaAM, не pyannote. Текст полного файла (разметка тогда была pyannote 3.1, **не пересчитывать**):

- `results/asr/2/gigaam_v3_rnnt/meeting_sample.json`
- копия `.txt`

Это гипотеза, не человеческий эталон. Пустые сегменты остаются пустыми. Не гонять заново полный файл, Whisper, Podlodka, gain, извлечение. Ошибки вроде «касторозительно» / «дальневосрочная» — вход, не повод чинить JSON.

**Диаризация демки.** Silero VAD (основной) + WeSpeaker ResNet34. Fallback **только в дырах** Silero: в исследовании выбран TEN (лучше хвост `test_voice`); для **коммерции TEN платный** (Agora non-compete / лицензия) — допустимая замена **FSMN** (FunASR ONNX; в 1f2b тоже давал текст в дырах Silero, чуть слабее TEN). Для внутренней/публичной **демо** TEN ок. В текущем коде demo fallback в дырах **ещё не подключён** (`vad.fallback: disabled`, движок-заглушка). ERes2Net-base и TitaNet-small на 4 клипах дали те же 2/3/2/2 — можно заменить WeSpeaker, в демке не тащим. Не sherpa-full, не pyannote 3.1 на клиентской машине.

**Фильтрация / шумодавы.** Не применяем. Linear gain этапа 2 остаётся единственной обработкой громкости.

**Таймкоды глав.** Только границы исходных ASR-сегментов: `start` первого листа, `end` последнего. LLM время не генерирует и не правит.

**Чанкинг.** Правильной нарезки нет. Пользователю достаточно ориентира «о чём говорили примерно тогда». Плотность — ориентир 0,4–0,8 главы/мин (на эту запись 8–20, лучше 12–18), крошка &lt;45 с и свалка &gt;180 с нежелательны, но не абсолютный закон.

---

## Итог этапов 2 и 2b

Прогон 2b: `origin/cursor/stage2b-four-hypotheses-4305`. TOC: `results/reports/2b/toc_c_vs_d.md`.

| Опыт | Глав | Вердикт |
|---|---:|---|
| A эмбеддинг 63 названий tiny2 | 62 | не рабочий |
| B попарный Qwen3-8B | 43 | не рабочий; ~27 мин, часто битый JSON |
| **C** packing разных спикеров (gap ≤2 с) + tiny2 0,70 | **14** | **рабочий** |
| **D** late chunking `jinaai/jina-embeddings-v3-hf` (порт той же Jina ~570M / 8192; официальный flash-чекпоинт не встал на transformers 5.16.1), окно 240 с / overlap 60 с | **12** | **рабочий** |

Победителя между C и D **нет**. Дальше тестируем оба как каркас TOC. Сравнение с `eval/test_timecodes.json` (большая модель, просили только смысловые куски, **без** лимита длительности) не выявило победителя: перекрытие ~0,81 vs 0,80, стыки с обеих сторон ~30 с. LLM дала 14 тем, в том числе крошку 12 с и кусок 201 с — это другой жанр (смысл), не судья плотности.

**Опциональный гибрид (не обязателен в первом прогоне 3):** сначала атомы как в C (разные спикеры в одном окне, gap ≤2 с), затем late chunking как в D той же моделью `jinaai/jina-embeddings-v3-hf` (окна 240/60 с, главы 45–180 с). Не усреднять два готовых оглавления.

Заголовки 8B на C/D «похожи на правду», но общие и тащат ASR-мусор. Основная ценность продукта — этап 3.

Не повторять: скрипты ASR этапа 2, три tiny2 «один спикер», one-shot склейку 63 названий, A/B как основной путь.

---

## Этап 3 — ключевые моменты, не «обсуждали тему»

Ориентир по жанру — локальный `eval/test_timecodes.json` (агентам не читать): не «совещание по сетям», а конкретность (подключение через паркинг; ждать экспертизу; письмо ресурсника; 10–12 кВт; корпус 9 не в корзину). Большой модели **не** задавали лимит длительности; у нас интервалы уже фиксированы (C/D).

Куски короткие (примерно 1–3 мин). Сначала **одна** модель: тот же **Qwen3-8B Q5**. Bakeoff LLM — только если 8B на этих кусках плодит штампы или выдумки. Аудио в API нет.

Название и инсайты — **разные вызовы**. Гипотеза: сначала факты, из них название. Иначе модель пишет общее «Обсуждение X» и подгоняет саммари.

### Что извлечь из каждой главы

Поля (таймкоды только копировать из chapter JSON):

- `key_points` — 2–6 конкретных тезисов: решение, цифра, условие, договорённость. Запрещены заготовки «обсудили / говорили о / совещание по».
- `actions` — только поручения и следующие шаги, которые есть в тексте; иначе `[]`.
- `open_questions` — неснятые вопросы из текста; иначе `[]`.
- `asr_notes` — опционально: «похоже на квартирографию», без правки исходного текста.
- `title` — ≤10 слов **после** инсайтов, по списку пунктов, не по сырому чанку заново.

Не invent timestamps, owners, цифры, которых нет в тексте (урок 1a «Разработчик»).

### Гипотезы промптов (не моделей)

Одна нарезка для сравнения промптов: **D (12 глав)**. C (14) — тем же победившим промптом, без второго bakeoff.

1. **P1 one-shot (контроль).** Один JSON: title + key_points + actions. Как большая модель, но на готовом интервале.
2. **P2 two-pass (основная).** Вызов 1: только key_points / actions / open_questions. Вызов 2: только title из этих пунктов (полный текст главы во второй вызов не давать).

Критерий на глаз: меньше штампов «обсуждение», больше проверяемых фактов, actions не выдуманы. 8B не судья самой себе.

Не делать в 3: новый ASR, шумодавы, новая нарезка, гибрид C→D, объявлять C или D истинными.

**Итог 3 (закрыт).** На D выбрали P1 для title (P2 копирует первую фразу и ASR-мусор в заголовок). Инсайты у обоих слабые (пропуск 10/12 кВт). Не эталон для SFT. Подробно: [`results/reports/3/notes.md`](../results/reports/3/notes.md).

---

## Этап 1f — лёгкая диаризация (сейчас)

Диаризация **обязательна** (C packing, метки спикеров). pyannote 3.1 + torch на 4 vCPU ~13 мин на 25 мин — главный тормоз, не GigaAM. Демка: **2 vCPU / 8 ГБ**, файл 20–30 мин, шаг «кто когда говорил» без `torch`. На жирной машине pyannote 3.1 остаётся потолком.

Не пересчитывать полный `results/asr/2/…` и не выбирать заново ASR. Полный `docs/Голос 002.m4a` не диаризовать в этом прогоне — только 4 уже вырезанных клипа.

Вход: [`docs/eval_clips.md`](eval_clips.md). Эталон меток **в git**: [`results/reports/1f/baseline/pyannote31/`](../results/reports/1f/baseline/pyannote31/) (копия 1e). Человеческое золото в `eval/` агентам не читать.

Порядок:

1. Два ONNX-аннотатора → таблица turns. Скрипт [`scripts/stage1f_compare_turns.py`](../scripts/stage1f_compare_turns.py) против pyannote 1e (DER с воротником 0,25 с, speech IoU).
2. Тот же GigaAM v3 на новых стыках. Текст pyannote+GigaAM не пересчитывать: [`results/reports/1f/baseline/gigaam_v3_on_pyannote/`](../results/reports/1f/baseline/gigaam_v3_on_pyannote/).

| id | Стек | Зачем |
|---|---|---|
| `pyannote31` | копия 1e, torch тогда | потолок; не запускать заново |
| `sherpa_onnx` | сегментация pyannote 3.0 ONNX + эмбеддинг + кластер, без torch | тот же класс, другой рантайм |
| `vad_wespeaker` | Silero VAD ONNX + WeSpeaker (`diarize` или руками) | другая нарезка речи |

VAD без спикеров в **1f** не кандидат (нужны id для packing C). Итог 1f: [`results/reports/1f/notes.md`](../results/reports/1f/notes.md) — для демки из коробки **vad_wespeaker**; sherpa дробит спикеров (5–8 id), зато IoU речи ~0,94. Wall на 4×85 с: vad_wespeaker **8,3 с** (Silero+WeSpeaker **вместе**, раздельно не логировали), sherpa **39 с**, pyannote 1e **~154 с**.

---

## Этап 1f2 — 3 VAD + 3 эмбеддера (закрыт, решение в conclusions)

«Дыры» в 1f считались относительно pyannote. Второй VAD нужен, чтобы увидеть, кто кого пропускает (начало/хвост `test_voice`). 1f не разделил wall Silero и WeSpeaker.

Те же 4 клипа. Промпт: [`docs/prompts/stage1f2_vad.md`](prompts/stage1f2_vad.md). Таблицы: [`results/reports/1f2/notes.md`](../results/reports/1f2/notes.md). Решение: [`results/reports/1f2/conclusions.md`](../results/reports/1f2/conclusions.md) — **Silero + fallback в дырах (TEN; коммерчески — FSMN) + WeSpeaker**. Пороги Silero в 1f2 не крутили.

**A — речь/тишина**

| id | Что |
|---|---|
| `silero` | тот же ONNX, **без** WeSpeaker; свой `runtime_sec` |
| `ten_vad` | TEN-framework |
| `fsmn_vad` | FunASR FSMN ONNX |

Попарный speech IoU и уникальные секунды. **Не** выбирать маску по max IoU vs pyannote. Нарезка для B всегда = Silero этого прогона.

**B — спикеры, одни куски, тот же кластер 1f**

| id | Что |
|---|---|
| `wespeaker` | ResNet34-LM, как в 1f, только embed+cluster |
| `eres2net` | 3D-Speaker ERes2Net-base ONNX (~38 МБ); не large, не ECAPA |
| `titanet_small` | NeMo TitaNet-small ONNX (~38 МБ); не Large |

Кластер: `cluster_embeddings` из [`scripts/run_stage1f.py`](../scripts/run_stage1f.py), пороги не крутить.

---

## Этап 1f2b — GigaAM на TEN / FSMN (закрыт)

Маски не пересчитывались. Промпт: [`docs/prompts/stage1f2_asr.md`](prompts/stage1f2_asr.md). Текст: [`asr_notes.md`](../results/reports/1f2/asr_notes.md). Silero не гоняли — [`results/asr/1f/vad_wespeaker/`](../results/asr/1f/vad_wespeaker/).

| id | Вход |
|---|---|
| `gigaam_ten` | `results/asr/1f2/ten_vad/` `speech_regions` |
| `gigaam_fsmn` | `results/asr/1f2/fsmn_vad/` `speech_regions` |

Спикер в сегментах = `SPEECH`. Смотреть текст окон `test_voice` 0–10 с и 75–83 с.

---

## Этап 3b — инсайты из markdown (закрыт)

Скрипт [`scripts/asr_json_to_md.py`](../scripts/asr_json_to_md.py) резал ASR по главам 2b. Промпт: [`docs/prompts/stage3b.md`](prompts/stage3b.md). Вход был 12 файлов `chunks_d/`. Gemini-экстракт — потолок; локальный 8B в 3b **собирал Gemini**, не экстрагировал заново. Self-check API сравнивал `src` реплик с часами глав — это не groundedness.

---

## Этап 3c — фильтр и два независимых прогона (закрыт)

Вход — **два файла**: [`data/3c_data/transcript.md`](../data/3c_data/transcript.md) (GigaAM + gold в четырёх окнах eval) и [`data/3c_data/chapters.json`](../data/3c_data/chapters.json) (часы D + `gold_windows`). Промпт: [`docs/prompts/stage3c.md`](prompts/stage3c.md). Скрипты: [`scripts/stage3c_pack.py`](../scripts/stage3c_pack.py), [`scripts/stage3c_run.py`](../scripts/stage3c_run.py), follow-up report — [`scripts/stage3d_report.py`](../scripts/stage3d_report.py).

**Итог.** Gemini 2.5 Flash — приемлемый потолок (инсайты + report). Qwen3-8B Q5 на 4 CPU — самостоятельный экстракт, но слабое обобщение: шум на extract, на report после ужесточения фильтра — перекос в другую сторону. Текстовый бар «2–3 реплики» / «≥3 реплики» одной формулировкой не решает задачу; отложено: другие модели (14B+, GPU), варианты промптов, возможно детерминированный постфильтр. Подробно: [`results/reports/3c/notes.md`](../results/reports/3c/notes.md).

**Прод — батчинг по чанкам.** На встрече 12 глав D; в проде — десятки чанков с **одним и тем же** extract-промптом. Последовательный цикл «глава → LLM», как в `stage3c_run.py`, на GPU/API не обязателен: llama.cpp batch, vLLM continuous batching или параллельные API-запросы дают существенный выигрыш по wall time. Саммари и короткий meeting-level report — после merge всех `insights.md`, не N+1 вызовов на каждый чанк для финальной сборки.

Local пишет свой экстракт (в отличие от 3b). **C не гоняем.** `eval/` агентам не читать.

---

## Потом — словарь после ASR

Не править замороженный JSON сейчас. Контур:

1. После ASR, до заголовков: сверка токенов с доменными словарями.
2. Предлагать замену (`suggested`, `confidence`, span + таймкод), не подменять молча.
3. Пачки: инженерный, финансовый, планировка/девелопмент (квартирография), IT — по мере записей.

Примеры с этой встречи: `касторография` → квартирография, `дальневосрочная` → дальневосточная.

---

## Эталонного полного текста нет

| Что | Путь | Эталон? |
|---|---|---|
| Полный ASR | `results/asr/2/gigaam_v3_rnnt/meeting_sample.json` | нет |
| 4 клипа | `eval/test_*.json` | да, ~85 с |
| Смысловой TOC большой модели | `eval/test_timecodes.json` | нет, третий голос |

---

# Архив

- 1b: не повторять afftdn и WhisperX-as-default.
- 2b протокол опытов: [`docs/prompts/stage2b_chunking.md`](prompts/stage2b_chunking.md).
- Оглавление 63 чанков этапа 2: [`results/reports/2/toc_attempt2.md`](../results/reports/2/toc_attempt2.md).

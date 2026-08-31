# Этап 1f2 — 3 VAD + 3 эмбеддера на замороженных Silero-срезах

Эталон меток — Stage 1e pyannote 3.1 (`results/reports/1f/baseline/pyannote31/`), **не** человеческое золото. `eval/` не читался. Решение стека — [`conclusions.md`](conclusions.md), не эта таблица.

Цель: отделить «дыры vs pyannote» (VAD) от «кто говорил» (эмбеддер + тот же кластер, что в 1f). В 1f Silero+WeSpeaker дали **один** wall (~8,3 с / 4 клипа).

## Среда

- Хост: 4 vCPU, 15 GiB RAM, без GPU. `OMP_NUM_THREADS` / `num_threads` = 2 (оценка демки 2 vCPU / 8 ГиБ).
- Клипы на месте: `data/test_{voice,apartments,transformers,ninth}.m4a` (83/85/85/85 с). Не перенарезались.
- Интерпретатор: `.venv-1f2` (не `.venv-onnx` / `.venv-gigaam` из 1f). **torch не установлен.**
- `results/asr/1f/` и `results/**/2/` не перезаписывались.
- Внешнее ASR/API не использовалось. Аудио в Gemini/NVIDIA не отправлялось.

## Установки

| Семейство | Попытка 1 | Попытка 2 |
|---|---|---|
| core ONNX | `numpy==1.26.4` (пин `funasr-onnx`), `onnxruntime 1.29.0`, `scikit-learn 1.6.1`, `soundfile` | не нужна |
| silero | тот же ONNX, что 1f (`models/silero_vad.onnx`) | не нужна |
| ten-vad | `pip install ten-vad` → 1.0.6.8; `CDLL` упал: нет `libc++.so.1` | `apt install libc++1 libc++abi1` → успех |
| fsmn_vad | `funasr-onnx 0.4.2` + HF `funasr/fsmn-vad-onnx` (переименованы `vad.yaml`→`config.yaml`/`model_conf`, `vad.mvn`→`am.mvn`). Torch не ставился | не нужна |
| wespeaker | `speakeronnx 0.0.1` `wespeaker-resnet34` | не нужна |
| eres2net / titanet | `sherpa-onnx 1.13.6` + ONNX с GitHub `speaker-recongition-models` | не нужна |

TEN-VAD: Apache-2.0 **с Agora non-compete** (LICENSE: нельзя Deploy так, чтобы конкурировать с offerings Agora). Прогон всё равно выполнен.

`runtime_sec` VAD = инференс + чтение уже готового 16 kHz WAV (общий ffmpeg-extract **не** входит в wall VAD). Эмбеддеры: `embed_runtime_sec` без VAD; `cluster_runtime_sec` отдельно.

## Фаза A — речь / не-речь

Маска Phase B **не** выбиралась по max IoU vs pyannote. Заморожен **Silero этого прогона** (`results/asr/1f2/silero/`). Fallback на 1f `vad_wespeaker` не понадобился.

| id | torch | Wall 4 клипа | Peak RSS | Регионы (v/a/t/n) | Речь, с (v/a/t/n) |
|---|---|---:|---:|---|---|
| `pyannote31` (эталон 1e) | да (тогда) | — | — | 4 / 5 / 6 / 8 | 63,10 / 61,44 / 72,80 / 74,54 |
| `silero` | нет | 0,785 с | 112 МиБ | 16 / 17 / 18 / 17 | 64,35 / 65,64 / 67,66 / 66,31 |
| `ten_vad` | нет | 1,600 с | 85 МиБ | 19 / 18 / 24 / 19 | 72,42 / 70,07 / 67,00 / 67,78 |
| `fsmn_vad` | нет | 1,109 с | 232 МиБ | 12 / 15 / 11 / 14 | 66,99 / 67,47 / 72,10 / 69,84 |

Попарный speech IoU (кадр 0,01 с):

| Клип | silero↔py | ten↔py | fsmn↔py | silero↔ten | silero↔fsmn | ten↔fsmn |
|---|---:|---:|---:|---:|---:|---:|
| `test_voice` | 0,777 | 0,759 | 0,761 | 0,835 | 0,746 | 0,804 |
| `test_apartments` | 0,728 | 0,766 | 0,719 | 0,878 | 0,824 | 0,833 |
| `test_transformers` | 0,848 | 0,825 | 0,871 | 0,919 | 0,839 | 0,838 |
| `test_ninth` | 0,884 | 0,897 | 0,878 | 0,930 | 0,857 | 0,872 |

Секунды, которые система кроет, а pyannote — нет / pyannote кроет, а система — нет:

| Клип | silero \ py | py \ silero | ten \ py | py \ ten | fsmn \ py | py \ fsmn |
|---|---:|---:|---:|---:|---:|---:|
| `test_voice` | 8,63 | 7,37 | 13,97 | 4,64 | 10,76 | 6,87 |
| `test_apartments` | 12,11 | 7,91 | 13,04 | 4,42 | 13,57 | 7,53 |
| `test_transformers` | 3,21 | 8,38 | 3,82 | 9,61 | 4,64 | 5,34 |
| `test_ninth` | 0,21 | 8,45 | 0,50 | 7,26 | 2,34 | 7,02 |

### `test_voice` 0–10 с и 75–83 с

| Окно | pyannote 3.1 | silero | ten_vad | fsmn_vad |
|---|---|---|---|---|
| 0–10 с | 0,03 с (только 9,970–10,000) | **8,36 с** (0,876–3,828; 4,588–10,000) | **7,79 с** (с ~0,90 и 4,54) | **5,64 с** (0,58–2,29; 4,71–6,10; 6,60–9,14) |
| 75–83 с | **0 с** | 0,09 с (75,000–75,092) | **5,90 с** (в т.ч. 78,53–83,00) | **3,88 с** (75,00–75,27; 78,51–79,67; 80,54–82,99) |

На хвосте 75–83 с pyannote молчит. TEN-VAD и FSMN кроют несколько секунд; Silero почти не кроет (0,09 с на границе 75,0). На старте 0–10 с все три VAD слышат речь, которую pyannote почти целиком пропускает.

## Фаза B — спикеры, одна и та же Silero-нарезка

Окна: `windows_for_segment` из 1f (чанки < 0,4 с пропуск). Кластер: `cluster_embeddings` из `scripts/run_stage1f.py` без re-tune. Склейка 1e/1f: gap ≤ 0,3 с того же спикера; turns < 1,0 с поглощаются. Эталон спикеров pyannote: **2 / 3 / 2 / 2**.

Число эмбеддингов на клип у всех трёх одно и то же: **102 / 106 / 105 / 105**.

| id | torch | embed wall 4 клипа | cluster wall (сумма) | Peak RSS | Спикеры (v/a/t/n) | Turns | mean DER@0,25 | speech IoU |
|---|---|---:|---:|---:|---|---|---:|---:|
| `wespeaker` ResNet34-LM | нет | 4,998 с | 1,433 с | 285 МиБ | **2 / 3 / 2 / 2** | 14 / 18 / 18 / 15 | 0,276 | 0,818 |
| `eres2net` base zh-cn | нет | 6,996 с | 0,748 с | 359 МиБ | **2 / 3 / 2 / 2** | 14 / 16 / 17 / 16 | 0,264 | 0,821 |
| `titanet_small` | нет | 3,273 с | 0,735 с | 368 МиБ | **2 / 3 / 2 / 2** | 14 / 16 / 18 / 16 | 0,271 | 0,818 |

По клипам (воротник 0,25 с; спикеры hyp vs эталон 2/3/2/2):

| Клип | wespeaker DER / IoU / turns | eres2net DER / IoU / turns | titanet DER / IoU / turns |
|---|---|---|---|
| `test_voice` | 0,232 / 0,793 / 14 | 0,232 / 0,793 / 14 | 0,232 / 0,793 / 14 |
| `test_apartments` | 0,514 / 0,722 / 18 | 0,503 / 0,722 / 16 | 0,493 / 0,722 / 16 |
| `test_transformers` | 0,184 / 0,842 / 18 | 0,192 / 0,842 / 17 | 0,184 / 0,842 / 18 |
| `test_ninth` | 0,173 / 0,915 / 15 | 0,130 / 0,925 / 16 | 0,177 / 0,913 / 16 |

На `test_voice` / `apartments` / `transformers` speech IoU **совпадает** между эмбеддерами (замороженные срезы). На `test_ninth` IoU чуть разъехался (0,915 / 0,925 / 0,913): `assemble_turns` + поглощение коротких turns меняет union речи, когда метки спикера разные — не смена VAD-маски.

Все три эмбеддера дали счётчик спикеров **2 / 3 / 2 / 2**, без over-split sherpa 1f (5 / 6 / 6 / 8). В 1f `vad_wespeaker` на apartments был 4 спикера; здесь на той же семье WeSpeaker — 3 (VAD-фрагменты склеены gap ≤ 0,3 с **до** окон, как задано для 1f2).

Confusion на `test_voice` = 0 у всех трёх (2 спикера). DER на apartments ~0,49–0,51 в основном confusion + FA относительно pyannote (Silero кроет +12 с, которых нет у 3.1).

## Артефакты

- `results/asr/1f2/{silero,ten_vad,fsmn_vad}/<clip>.json` — `speech_regions` (speaker=`SPEECH`)
- `results/asr/1f2/{wespeaker,eres2net,titanet_small}/<clip>.json` — `raw_turns` + `merged_turns`
- `results/reports/1f2/speech_iou.json`
- `results/reports/1f2/turn_compare.json`
- WAV 16 kHz: `results/asr/1f2/_extracts/` (gitignored)

## Вне скоупа (1f2, маски)

Этап 3 LLM, словарь, шумодавы, новый чанкинг, полная запись, WER. Решение стека — [`conclusions.md`](conclusions.md).

## Указатель 1f2b — текст GigaAM на TEN / FSMN

Таблицы VAD и эмбеддеров **не** менялись. Распознавание замороженных `speech_regions`: [`asr_notes.md`](asr_notes.md). JSON: `results/asr/1f2/gigaam_ten/`, `results/asr/1f2/gigaam_fsmn/`. Silero-текст не гонялся повторно — `results/asr/1f/vad_wespeaker/`. На `test_voice` 75–83 с у Silero текста нет; TEN/FSMN дали фразы про техусловия / проектирование.

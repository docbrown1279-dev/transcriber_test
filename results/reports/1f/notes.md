# Этап 1f — ONNX-диаризация vs pyannote 3.1 на 4 eval-клипах

Эталон меток — Stage 1e pyannote 3.1 (`results/reports/1f/baseline/pyannote31/`), **не** человеческое золото. `eval/` не читался, WER не считался.

## Среда

- Хост: 4 vCPU, 15 GiB RAM, без GPU. Для ONNX-диаризаторов `OMP`/`num_threads` = 2 (оценка демки 2 vCPU / 8 ГиБ).
- Клипы на месте: `data/test_{voice,apartments,transformers,ninth}.m4a` (83/85/85/85 с). Не перенарезались.
- Два интерпретатора: `.venv-onnx` **без torch**; `.venv-gigaam` с CPU-torch только для GigaAM.
- Внешнее ASR/API не использовалось. Аудио в Gemini/NVIDIA не отправлялось.

## Установки

| Семейство | Попытка 1 | Попытка 2 |
|---|---|---|
| sherpa-onnx | `pip install sherpa-onnx` → 1.13.6, успех | не нужна |
| vad_wespeaker | не пакет `diarize` (тянет torch). Silero VAD ONNX + `speakeronnx` WeSpeaker ResNet34-LM + sklearn clustering | не нужна |
| GigaAM | `gigaam==0.2.0` с PyPI — нет такого релиза | `git+https://github.com/salute-developers/GigaAM.git` → 0.2.0, успех |

Версии ONNX-venv: `sherpa-onnx 1.13.6`, `onnxruntime 1.29.0`, `speakeronnx 0.0.1`, `scikit-learn 1.9.0`, `numpy 2.5.2`.  
Версии ASR-venv: `gigaam 0.2.0`, `torch 2.13.0+cpu`, `torchaudio 2.11.0+cpu`. CUDA нет.

Модели (кэш `models/`, не в git): pyannote segmentation 3.0 ONNX, 3D-Speaker ERes2Net zh-cn, `silero_vad.onnx`, HuggingFace `Wespeaker/wespeaker-voxceleb-resnet34-LM`.

## Порядок

1. Копия эталона `pyannote31` + текста GigaAM v3 с 1e. `pyannote.audio` / torch для 3.1 не загружались.
2. `sherpa_onnx` и `vad_wespeaker` на исходных M4A (без file-level loudnorm). Часы клипа: 0 = начало m4a.
3. Склейка как в 1e: gap ≤ 0,3 с того же спикера; turns < 1,0 с поглощаются. Дыры ≥ 0,5 с записаны.
4. `scripts/stage1f_compare_turns.py` → `results/reports/1f/turn_compare.json` (воротник 0,25 с).
5. Извлечение merged-строк, линейный `volume=` только если RMS < −30 dBFS (как 1e). GigaAM `v3_rnnt` на CPU. Строки > 25 с резались только по времени.

## Диаризация (метки)

| id | torch | Wall 4 клипа | Peak RSS | Спикеры (v/a/t/n) | Turns | mean DER@0,25 | speech IoU |
|---|---|---:|---:|---|---|---:|---:|
| `pyannote31` (эталон 1e) | да (тогда) | 153,9 с | — | 2 / 3 / 2 / 2 | 4 / 12 / 9 / 16 | — | — |
| `sherpa_onnx` | нет | 39,1 с | 382 МиБ | 5 / 6 / 6 / 8 | 6 / 12 / 11 / 19 | 0,320 | 0,942 |
| `vad_wespeaker` | нет | 8,3 с | 242 МиБ | 2 / 4 / 2 / 2 | 14 / 21 / 18 / 16 | 0,296 | 0,813 |

По клипам (воротник 0,25 с):

| Клип | sherpa DER / IoU / spk | vad_wespeaker DER / IoU / spk |
|---|---|---|
| `test_voice` | 0,247 / 0,969 / 5 | 0,232 / 0,793 / 2 |
| `test_apartments` | 0,397 / 0,876 / 6 | 0,618 / 0,703 / 4 |
| `test_transformers` | 0,339 / 0,943 / 6 | 0,184 / 0,842 / 2 |
| `test_ninth` | 0,298 / 0,978 / 8 | 0,152 / 0,915 / 2 |

Наблюдения:

- **sherpa_onnx** почти копирует речевые интервалы pyannote (IoU ~0,94; miss почти 0). DER в основном confusion: дефолтный `cluster_threshold=0.5` дробит 2–3 спикеров на 5–8 id. Порог не крутили (нет re-tune в 1f).
- **vad_wespeaker** ближе по числу спикеров (2–4). На `test_voice` confusion = 0 при 2 спикерах; VAD находит речь в начале клипа, которую pyannote 3.1 пропускает (~0–10 с) — отсюда FA/miss относительно эталона, не обязательно ошибка относительно золота. На `test_apartments` хуже всех (DER 0,62). Нарезка мельче (больше turns), packing C это переживёт.
- VAD без спикер-id не использовался.

## GigaAM v3 (текст)

Тот же `v3_rnnt`, CPU. pyannote-текст — копия 1e, не пересчитывался.

| id | ASR wall (сумма клипов) | segs | пустые |
|---|---:|---:|---:|
| `pyannote31` (копия) | 16,0 с | 5 / 12 / 9 / 16 | 0 / 0 / 1 / 0 |
| `sherpa_onnx` | 29,9 с | 7 / 12 / 11 / 19 | 0 / 0 / 1 / 0 |
| `vad_wespeaker` | 33,7 с | 14 / 21 / 18 / 16 | 1 / 0 / 1 / 0 |

По клипам ASR с: voice 5,4 / 7,2 с; apartments 7,5 / 9,4; transformers 7,3 / 8,6; ninth 9,7 / 8,5 (sherpa / vad). Gain linear на тихих строках. Полные транскрипты в notes не копируются.

## 2 vCPU / 8 ГиБ vs жирная машина

- Оба ONNX-стека укладываются в память с запасом (240–380 МиБ peak RSS на 85 с, без torch в процессе). На 2 потоках 4×~85 с диаризации: ~8 с (VAD+WeSpeaker) и ~39 с (sherpa). Это правдоподобно для демки 20–30 мин: грубо ×15–20 → порядка 2–3 мин sherpa и <1 мин vad_wespeaker, плюс GigaAM (в 1e RTF ≈ 0,035).
- **Демка 2c/8ГБ:** `vad_wespeaker` — единственный из двух, у кого число спикеров не разъезжается. Torch в процессе нет. Качество нарезки речи слабее pyannote; для каркаса C (packing по спикерам) это приемлемый кандидат, если дальше смотреть WER глазами.
- **sherpa_onnx** без подкрутки кластера не годится как аннотатор «кто говорил»: id слишком много. Речевые границы близки к 3.1 — после nudge порога (больше 0,5) это кандидат «тот же класс, другой рантайм». В этом прогоне не трогали.
- **pyannote 3.1 + torch** остаётся потолком качества на жирной машине (~39 с/клип на 4 vCPU в 1e). В 1f не запускался.

## Артефакты

- `results/asr/1f/{pyannote31,sherpa_onnx,vad_wespeaker}/<clip>.json`
- `results/reports/1f/turn_compare.json`
- WAV-extracts в `results/asr/1f/_extracts/` (gitignored)

## Вне скоупа

Этап 3 LLM, словарь, шумодавы, новый чанкинг, полная запись, объявление C/D единственным TOC, API LLM.

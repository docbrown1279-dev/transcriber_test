# Тикет: GigaAM v3 ONNX (место на диске / без torch)

**Статус:** OPEN (backlog)  
**Приоритет:** средний — после стабильного шипа 15′; не блокирует демо.  
**Связано:** размер Docker-образа (~2 ГБ, львиная доля `torch`); extras `asr` в `pyproject.toml`.

---

## Контекст

Официальный Salute GigaAM ([репо / changelog](https://github.com/salute-developers/GigaAM)):

- с **2024/12 (v2)** заявлен **ONNX export**;
- **v3** (2025/11) заметно лучше по доменам / e2e; в демке зафиксирован **`gigaam_v3_rnnt` + torch**.

В ранних прогонах смотрели v2; для продукта держим **v3**.

Сообщество: конвертация v3 → ONNX для [`onnx-asr`](https://github.com/istupakov/onnx-asr):

- модель: [`istupakov/gigaam-v3-onnx`](https://huggingface.co/istupakov/gigaam-v3-onnx) (MIT)
- варианты: `gigaam-v3-ctc`, `gigaam-v3-rnnt`, `gigaam-v3-e2e-ctc`, `gigaam-v3-e2e-rnnt`
- установка: `pip install onnx-asr[cpu,hub]`

Экспорт в карточке модели — через официальный `gigaam.load_model(...).to_onnx(...)` (нужен torch **на машине экспорта**, не обязательно в runtime-образе демки).

Локальный `.venv` (ориентир): `torch` ~740 МБ, `transformers` ~60 МБ (это **rubert**/ST, не GigaAM). Снятие torch из runtime — главный выигрыш по диску.

---

## Цель

1. Проверить **качество** ONNX v3 RNNT (или e2e-rnnt) vs текущий torch `v3_rnnt` на тех же 4 eval-клипах / срезе voice_002 (WER глазами + русский word ratio; без пересчёта полного stage2 эталона без нужды).
2. Если паритет приемлемый — порт `AsrEngine` / опциональный `gigaam_v3_rnnt_onnx`, профиль demo без torch в образе.
3. Замерить: размер image, peak RSS, wall ASR на 15′ @ 2 CPU.

---

## Не делать в этом тикете

- Менять зафиксированный стек «по умолчанию» без gate по качеству.
- Тянуть e2e только ради пунктуации, если RNNT-ONNX уже ок.
- Путать с ONNX **эмбеддингов глав** (rubert) — отдельный маленький follow-up: stub `bge_small_onnx` в registry.

---

## Критерии done

| id | критерий |
|---|---|
| Q1 | Таблица: torch v3_rnnt vs onnx v3_rnnt (клипы + заметки по дырам/именам) |
| Q2 | Решение: demo default / opt-in / reject |
| Q3 | Если go: образ без torch (или optional extra), `healthz` + soft regression |

---

## Ссылки

- HF: https://huggingface.co/istupakov/gigaam-v3-onnx  
- План диска/deps: обсуждение после D5 ship; diarize TTFT — [`draft_ttft_diarize_split.md`](draft_ttft_diarize_split.md)

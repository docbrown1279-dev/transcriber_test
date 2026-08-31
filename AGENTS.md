# AGENTS.md — исследование распознавания речи

## Задача

Этап **1f** (сейчас): лёгкая диаризация (ONNX, без torch) на тех же 4 eval-клипах, что в 1e. Эталон меток — pyannote 3.1 из 1e (не человеческое золото). ASR полного файла и нарезка 2b заморожены. Этап 3 закрыт.

## Роль

Читать [`docs/research_plan.md`](docs/research_plan.md), [`docs/eval_clips.md`](docs/eval_clips.md), [`docs/prompts/stage1f_diarization.md`](docs/prompts/stage1f_diarization.md).

## Текущий этап (1f)

| В скоупе | Вне скоупа |
|---|---|
| `sherpa_onnx` и `vad_wespeaker` на `data/test_*.m4a` | Новый pyannote 3.1; полный `Голос 002` |
| Сначала сравнение **меток** с `results/reports/1f/baseline/pyannote31/` | Чтение `eval/`; WER считает человек |
| Потом тот же GigaAM v3 на новых turns | Whisper, Podlodka, шумодавы, этап 3 LLM |
| `results/reports/1f/` | Выбор победителя C/D; словарь |

## Критерий

ONNX-разметка достаточно близка к 1e pyannote, чтобы C packing по спикерам ещё работал, и чтобы GigaAM на этих стыках не развалился. Потолок качества — pyannote на жирной машине.

# AGENTS.md — исследование распознавания речи

## Задача

Этап **1f2b** (сейчас): GigaAM v3 на уже готовых масках TEN и FSMN. Разметка 1f / 1f2 закрыта. Полный ASR и нарезка 2b заморожены.

## Роль

Читать [`docs/research_plan.md`](docs/research_plan.md), [`docs/prompts/stage1f2_asr.md`](docs/prompts/stage1f2_asr.md), [`results/reports/1f2/notes.md`](results/reports/1f2/notes.md). Не читать `eval/`.

## Текущий этап (1f2b)

| В скоупе | Вне скоупа |
|---|---|
| GigaAM `v3_rnnt` на `results/asr/1f2/{ten_vad,fsmn_vad}/` | Новый VAD / эмбеддер / sherpa / pyannote 3.1 |
| `results/asr/1f2/{gigaam_ten,gigaam_fsmn}/` | Пересчёт Silero (текст уже в `results/asr/1f/vad_wespeaker/`) |
| Цитаты окон `test_voice` 0–10 с и 75–83 с | Чтение `eval/`; WER; этап 3 |

## Критерий

На хвосте `test_voice` 75–83 с есть текст TEN (и FSMN, если маска не пустая). Silero там почти молчал — его не гоняем заново.

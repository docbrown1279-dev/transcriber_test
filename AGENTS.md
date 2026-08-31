# AGENTS.md — исследование распознавания речи

## Задача

Этап **1f2** (сейчас): одним прогоном **3 VAD + 3 эмбеддера** на тех же 4 eval-клипах. 1f закрыт. Полный ASR и нарезка 2b заморожены. Победителя глазами смотрим после.

## Роль

Читать [`docs/research_plan.md`](docs/research_plan.md), [`docs/prompts/stage1f2_vad.md`](docs/prompts/stage1f2_vad.md), [`results/reports/1f/notes.md`](results/reports/1f/notes.md).

## Текущий этап (1f2)

| В скоупе | Вне скоупа |
|---|---|
| VAD: Silero, TEN, FSMN | sherpa full, pyannote 3.1, GigaAM, ECAPA |
| Эмбеддеры на **одних** Silero-кусках: WeSpeaker, ERes2Net-base, TitaNet-small | Новый кластер / re-tune порогов |
| Speech IoU, DER@0,25 vs pyannote 1e | Чтение `eval/`; WER |
| `results/reports/1f2/` | Полный `Голос 002` |

## Критерий

Один агент, без паузы: маски → всегда Silero как нарезка для B → три эмбеддера. Не выбирать VAD по max IoU vs pyannote. Человек потом смотрит дыры `test_voice` 0–10 с и 75–83 с и число спикеров.

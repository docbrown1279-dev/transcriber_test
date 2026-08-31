# AGENTS.md — исследование распознавания речи

## Задача

Этапы **1f / 1f2 / 1f2b закрыты.** Стек демки зафиксирован. Полный ASR и нарезка 2b заморожены. Дальше — словарь после ASR, не новый bakeoff VAD.

## Роль

Читать [`docs/research_plan.md`](docs/research_plan.md), [`results/reports/1f2/conclusions.md`](results/reports/1f2/conclusions.md). Не читать `eval/`.

## Зафиксировано (демка)

| Слой | Что |
|---|---|
| VAD | Silero основной, TEN только в дырах Silero |
| спикеры | WeSpeaker ResNet34 (ERes2Net / TitaNet на выборке те же 2/3/2/2 — можно, не тащим) |
| ASR | GigaAM `v3_rnnt` + CPU-torch; linear gain |

Не пересчитывать `results/asr/2/`, `results/asr/1f/`, маски 1f2. Не подставлять ECAPA / sherpa-full / pyannote 3.1 в демку.

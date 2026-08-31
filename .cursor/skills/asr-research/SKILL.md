---
name: asr-research
description: Этапы 1f/1f2 закрыты. Демка: Silero + TEN в дырах + WeSpeaker + GigaAM v3. Не читать eval/. Не пересчитывать полный файл.
---

# Исследование — после 1f2

## Стек

- VAD: Silero, TEN только в дырах Silero.
- Спикеры: WeSpeaker. ERes2Net-base и TitaNet-small на 4 клипах дали те же 2/3/2/2 — взаимозаменяемы, в демке не нужны.
- ASR: GigaAM v3 (torch = рантайм ASR, не pyannote).

Итог: [`results/reports/1f2/conclusions.md`](../../../results/reports/1f2/conclusions.md).

Не читать `eval/`. Не перезаписывать `results/asr/1f/` и `results/**/2/`. Не открывать новый bakeoff VAD/эмбеддеров без явной просьбы.

---
name: asr-research
description: Этап 1f — ONNX-диаризация vs pyannote 3.1 на 4 eval-клипах, затем GigaAM v3. Полный ASR и чанкинг заморожены.
---

# Исследование — этап 1f

## Цель

Заменить тяжёлый pyannote.audio+torch на CPU-ONNX для демки 2c/8 ГБ, не ломая нарезку спикеров.

## Чеклист

```
- [ ] Не пересчитывать pyannote 3.1; эталон в results/reports/1f/baseline/pyannote31/
- [ ] sherpa_onnx на 4 клипах
- [ ] vad_wespeaker на 4 клипах
- [ ] scripts/stage1f_compare_turns.py → results/reports/1f/turn_compare.json
- [ ] GigaAM v3 на новых turns; pyannote+GigaAM только копия baseline
- [ ] notes.md + research_report.json
```

Не читать `eval/`. Не трогать `results/**/2/`. Не гонять этап 3.

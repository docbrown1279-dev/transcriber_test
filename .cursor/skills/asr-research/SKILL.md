---
name: asr-research
description: Этап 1f2 — 3 VAD (Silero, TEN, FSMN) + 3 эмбеддера (WeSpeaker, ERes2Net-base, TitaNet-small) на 4 eval-клипах. Без GigaAM. 1f закрыт.
---

# Исследование — этап 1f2

## Цель

Одним прогоном: кто ловит речь в дырах pyannote, и какой ONNX-эмбеддер лучше клеит спикеров на **тех же** Silero-кусках. Кластеризацию 1f не крутить.

## Чеклист

```
- [ ] silero / ten_vad / fsmn_vad; speech_iou.json
- [ ] нарезка B = Silero этого прогона (не max IoU vs pyannote)
- [ ] wespeaker / eres2net / titanet_small; тот же cluster_embeddings из run_stage1f.py
- [ ] turn_compare.json vs pyannote 3.1
- [ ] notes.md + research_report.json в results/reports/1f2/
```

Не читать `eval/`. Не перезаписывать `results/asr/1f/` и `results/**/2/`. Не гонять GigaAM / этап 3. Не подставлять ECAPA.

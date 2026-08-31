---
name: asr-research
description: Этап 1f2b — GigaAM v3 на готовых масках TEN и FSMN. Разметка 1f2 закрыта. Не читать eval/.
---

# Исследование — этап 1f2b

## Цель

Получить текст с нарезки TEN/FSMN (особенно `test_voice` 75–83 с). VAD и эмбеддеры не пересчитывать. Silero+GigaAM уже есть в 1f `vad_wespeaker`.

## Чеклист

```
- [ ] .venv-gigaam (не .venv-1f2)
- [ ] gigaam_ten / gigaam_fsmn из speech_regions
- [ ] asr_notes.md: окна 0–10 с и 75–83 с
- [ ] не трогать results/asr/1f/ и JSON VAD 1f2
```

Не читать `eval/`. Не гонять этап 3. Не ставить GigaAM в ONNX-venv.

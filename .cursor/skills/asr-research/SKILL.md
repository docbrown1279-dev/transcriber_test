---
name: asr-research
description: Этап 3c — фильтрованные инсайты по чанкам 2b (D). Gemini и локальный Qwen независимо. Не читать eval/.
---

# Этап 3c

Промпт: [`docs/prompts/stage3c.md`](../../../docs/prompts/stage3c.md).

```
- [ ] вход только data/3c_data/transcript.md + chapters.json (gold в 4 окнах; не eval/, не C)
- [ ] gemini/insights.md + gemini/summary.md
- [ ] local/insights.md + local/summary.md (свой экстракт, не сборка Gemini)
- [ ] фильтр: 2–3 реплики / вопрос–ответ / развилка
- [ ] Gemini 5 попыток, лог без ключей; иначе NVIDIA 5
- [ ] follow-up без нового экстракта: docs/prompts/stage3c_report.md → report.md (спикеры + часы)
```

Не читать `eval/`. Не пересчитывать ASR/VAD/нарезку. Не перезаписывать `insights.md`.

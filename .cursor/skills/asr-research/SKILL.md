---
name: asr-research
description: Этап 3b — инсайты по чанкам 2b (D), отчёт, self-check. Сначала Gemini/NVIDIA с ретраями. Не читать eval/.
---

# Этап 3b

Промпт: [`docs/prompts/stage3b.md`](../../../docs/prompts/stage3b.md).

```
- [ ] экстрактор на data/3b_data/chunks_d/D*.md (не весь hybrid, не C)
- [ ] insights: # title + kind/src/text
- [ ] report.md + self_check.md
- [ ] Gemini 5 попыток, лог без ключей; иначе NVIDIA 5
- [ ] local 8B только если usable
```

Не читать `eval/`. Не пересчитывать ASR/VAD/нарезку.

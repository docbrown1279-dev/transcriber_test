# AGENTS.md — исследование распознавания речи

## Задача

Этап **3c**: фильтрованные инсайты по чанкам **2b-D (Jina)**. Два независимых прогона — Gemini API и локальный Qwen. C не гоняем. 3b закрыт (не перезаписывать).

## Роль

Читать [`docs/prompts/stage3c.md`](docs/prompts/stage3c.md). Не читать `eval/` и `.env`. Не открывать `data/3b_data/`.

## Вход / выход

| Агенту | Не читать |
|---|---|
| `data/3c_data/transcript.md` | `data/3b_data/`, hybrid, C, `eval/` |
| `data/3c_data/chapters.json` | весь `results/llm/3b/` на запись |

Выход: `results/llm/3c/gemini/{insights,summary}.md` и `results/llm/3c/local/{insights,summary}.md`. Local **не** копирует Gemini.

Сначала Gemini (5 попыток, лог ошибок), иначе NVIDIA (ещё 5). Потом локальный 8B — полный экстракт, не дым.

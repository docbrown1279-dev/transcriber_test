# AGENTS.md — исследование распознавания речи

## Задача

Этап **3c**: фильтрованные инсайты по чанкам **2b-D (Jina)**. Два независимых прогона — Gemini API и локальный Qwen. C не гоняем. 3b закрыт (не перезаписывать).

## Роль

Читать [`docs/prompts/stage3c.md`](docs/prompts/stage3c.md). Не читать `eval/` и `.env`. Не открывать `data/3b_data/`.

## Вход / выход

| Агенту | Не читать |
|---|---|
| `data/3c_data/transcript.md` | `data/3b_data/`, C, `eval/` |
| `data/3c_data/chapters.json` | весь `results/llm/3b/` на запись |

Выход экстракта (уже есть, не перезаписывать): `results/llm/3c/{gemini,local}/insights.md`.

Если просят спикеров и таймкоды в отчёте — [`docs/prompts/stage3c_report.md`](docs/prompts/stage3c_report.md): один assemble, `report.md` рядом, `insights.md` не трогать.

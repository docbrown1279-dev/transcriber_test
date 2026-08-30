# AGENTS.md — исследование распознавания речи

## Задача

Этап **3** (сейчас): LLM на **готовых** главах C и D. ASR, шумодавы и нарезка 2b не пересчитывать. Победителя между C и D не выбирать.

## Роль

Ты агент-**исследователь**. Читать:

1. [`docs/research_plan.md`](docs/research_plan.md) — стек и итог 2/2b
2. [`results/reports/2b/conclusions.md`](results/reports/2b/conclusions.md) — зафиксированные выводы
3. [`.cursor/skills/asr-research/SKILL.md`](.cursor/skills/asr-research/SKILL.md)
4. [`docs/prompts/stage3_llm.md`](docs/prompts/stage3_llm.md)

Не запускать заново этап 2 / 2b скрипты ASR и чанкинга. Пути `results/**/2/` и готовые `results/chunking/2b/exp_{c,d}_chapters.json` не перезаписывать.

## Текущий этап (3)

| В скоупе | Вне скоупа |
|---|---|
| Заголовки и саммари на главах C (14) и D (12) | Новый ASR, pyannote, gain, правка стенограммы |
| Сравнение LLM на **одинаковых** готовых интервалах | Выбор «правильной» нарезки; one-shot 63 id |
| Таймкоды только копировать из chapter JSON | Таймкоды от LLM; шумодавы; полное перенарезание |
| Отчёт `results/reports/3/` | Аудио в API; гибрид C→D без явной просьбы |

## Фикстуры

| Путь | Описание |
|---|---|
| `results/asr/2/gigaam_v3_rnnt/meeting_sample.json` | Замороженный полный текст |
| `results/chunking/2b/exp_c_chapters.json` | Рабочий каркас C |
| `results/chunking/2b/exp_d_chapters.json` | Рабочий каркас D |
| `data/fixtures/meeting_sample.m4a` | Аудио; в модели не слать |

## Секреты

Не печатать и не коммитить. `eval/` не читать и не коммитить. Gemini/NVIDIA — только если явно разрешат текст (не аудио).

## Критерий успеха 3

На C и на D отдельно: читаемые названия + саммари без новых границ. Факты, которых нет в тексте, помечены. Этап 2 не открывать заново.

## Без присмотра

Отчёты по-русски. Не force-push в `main`.

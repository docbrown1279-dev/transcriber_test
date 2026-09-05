# Meeting transcriber (demo)

Разработка приложения для **протоколирования русских совещаний**: аудио → ASR → чанки → LLM-отчёт → простой веб UI.

Репозиторий: [`docbrown1279-dev/transcriber_test`](https://github.com/docbrown1279-dev/transcriber_test).

Исследование стека **закрыто** (решения зафиксированы). Сейчас идёт **продуктовая разработка** профиля `demo` по этапам D0 → D5.

## Статус

| Этап | Смысл | Статус |
|---|---|---|
| **D0** | Каркас: конфиги, порты/заглушки, CLI, `/healthz` | **готово** (в `main`, gate PASS) |
| D1 | Голос → транскрипт (GigaAM + лёгкая диаризация) | следующий |
| D2 | Чанки + названия | — |
| D3 | Саммари и ключевые моменты (LLM) | — |
| D4 | Веб UI (Jinja) | — |
| D5 | Прогон на 2 vCPU / 8 ГБ | — |

Текущий прогресс: [`agent_docs/progress/stage_D0.md`](agent_docs/progress/stage_D0.md) · журнал: [`agent_docs/progress/log.md`](agent_docs/progress/log.md)  
Отчёт шлюза D0: [`agent_docs/reports/D0/gate_D0.md`](agent_docs/reports/D0/gate_D0.md)

План разработки: [`agent_docs/plans/draft_demo_roadmap.md`](agent_docs/plans/draft_demo_roadmap.md)

## Контракты (спека для агентов)

Индекс: [`agent_docs/contracts/index.md`](agent_docs/contracts/index.md)

| Документ | О чём |
|---|---|
| [`pipeline_artifacts.md`](agent_docs/contracts/pipeline_artifacts.md) | JSON-артефакты пайплайна |
| [`module_interfaces.md`](agent_docs/contracts/module_interfaces.md) | порты, реестр, заглушки |
| [`config_profiles.md`](agent_docs/contracts/config_profiles.md) | профили `demo` / `dev` / `prod` |
| [`quality_gates.md`](agent_docs/contracts/quality_gates.md) | автошлюзы G0–G5 |

## Мануалы (для человека)

Индекс: [`manuals/index.md`](manuals/index.md)

| Документ | О чём |
|---|---|
| [`cloud_flow.md`](manuals/cloud_flow.md) | облачный цикл: `/cloud_push`, `/cloud_pull` |
| [`manual_testing.md`](manuals/manual_testing.md) | ручная проверка / smoke по этапам |
| [`configuration_guide.md`](manuals/configuration_guide.md) | YAML-профили и `APP_PROFILE` |

## Быстрый старт (локально, после D0)

```bash
uv sync
export JOB_IP_SALT=local-dev-salt
uv run transcriber healthcheck
uv run pytest tests/ -v
```

Подробнее — в [`manuals/manual_testing.md`](manuals/manual_testing.md).

## Облачная разработка

1. Planner упаковывает этап в `cloud_in/`.
2. Локально: `/cloud_push` → Cloud Agent на указанной ветке.
3. После прогона: `/cloud_pull` (отчёты, затем код при PASS) → draft PR → merge.

Роль облачного агента: `cloud_in/agent/AGENTS.md` (не путать с архивом исследования).

## Стек демки (зафиксирован исследованием)

Silero VAD → WeSpeaker ONNX → GigaAM `v3_rnnt` → chunking C (`rubert-tiny2`) → Gemini (облако) / Qwen локально в `dev`. Шумодав не используем. Кратко: `cloud_in/inputs/STACK.md`.

Архив отчётов исследования (read-only, локально): `docs/research_results/` — облачным агентам не нужен.

# Meeting transcriber (demo)

Разработка приложения для **протоколирования русских совещаний**: аудио → ASR → чанки → LLM-отчёт → простой веб UI.

Репозиторий: [`docbrown1279-dev/transcriber_test`](https://github.com/docbrown1279-dev/transcriber_test).

Исследование стека **закрыто** (решения зафиксированы). Сейчас идёт **продуктовая разработка** профиля `demo` по этапам D0 → D5.

## Статус

| Этап | Смысл | Статус |
|---|---|---|
| **D0** | Каркас: конфиги, порты/заглушки, CLI, `/healthz` | **готово** (в `main`, gate PASS) |
| **D1** | Голос → транскрипт (GigaAM + WeSpeaker) | **готово** (HUMAN_GATE PASS) |
| **D2** | Чанки + названия | **готово** (HUMAN_GATE PASS) |
| **D3** | Саммари и ключевые моменты (LLM) | **готово** (HUMAN_GATE PASS) |
| **D4** | Веб UI (Jinja): загрузка → оглавление → глава | **в main** (локальная демка; HUMAN_GATE в браузере) |
| D5 | Прогон на 2 vCPU / 8 ГБ | следующий |

Текущий прогресс: [`agent_docs/progress/stage_D4.md`](agent_docs/progress/stage_D4.md) · журнал: [`agent_docs/progress/log.md`](agent_docs/progress/log.md)

План разработки: [`agent_docs/plans/draft_demo_roadmap.md`](agent_docs/plans/draft_demo_roadmap.md)  
Открытые тикеты: [`ticket_d1_gigaam_missing.md`](agent_docs/plans/ticket_d1_gigaam_missing.md), [`ticket_d1_speaker_clusters.md`](agent_docs/plans/ticket_d1_speaker_clusters.md), [`ticket_d2_short_chapters.md`](agent_docs/plans/ticket_d2_short_chapters.md), [`ticket_d4_audio_formats.md`](agent_docs/plans/ticket_d4_audio_formats.md)

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
| [`manual_testing.md`](manuals/manual_testing.md) | ручная проверка / smoke по этапам, **демо UI (D4)** |
| [`configuration_guide.md`](manuals/configuration_guide.md) | YAML-профили (`app.profile`) и секреты |
| [`llm.md`](manuals/llm.md) | бэкенды, промпты, лимит саммари в UI |

## Быстрый старт (локально)

```bash
uv sync
export JOB_IP_SALT=local-dev-salt   # обязателен; не коммитить .env
uv run transcriber healthcheck
uv run transcriber serve --reload   # http://127.0.0.1:8000/
```

Профиль — `config/base.yaml` → `app.profile` (`demo`). Демо LLM — **Qwen** (`config/profiles/demo.yaml`); для названий глав и кнопки саммари нужен `QWEN_API_KEY`. Подробнее: [`manuals/manual_testing.md`](manuals/manual_testing.md) (раздел D4) и [`manuals/configuration_guide.md`](manuals/configuration_guide.md).

## Облачная разработка

D4 делали **локально**, без cloud handoff. Облачный цикл (D0–D3) по-прежнему: Planner → `/cloud_push` → `/cloud_pull`.

Роль облачного агента: `cloud_in/agent/AGENTS.md` (не путать с архивом исследования).

## Стек демки (зафиксирован исследованием)

Silero VAD → WeSpeaker ONNX → GigaAM `v3_rnnt` → chunking C (`rubert-tiny2`) → в профиле **demo** LLM = **Qwen** (Gemini остаётся в `base_llm.yaml` и оверлеях `dev`/`prod`). Шумодав не используем.

Архив отчётов исследования (read-only, локально): `docs/research_results/` — облачным агентам не нужен.

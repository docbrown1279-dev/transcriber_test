# Meeting transcriber

Протоколирование русских совещаний: аудио → ASR → главы → LLM-отчёт → веб UI.

Репозиторий: [`docbrown1279-dev/transcriber_test`](https://github.com/docbrown1279-dev/transcriber_test).

## Документация

| Для кого | Куда |
|---|---|
| Человек (мануалы) | [`manuals/index.md`](manuals/index.md) |
| Конфиги и секреты | [`manuals/configuration_guide.md`](manuals/configuration_guide.md) |
| Ручная проверка / демо UI | [`manuals/manual_testing.md`](manuals/manual_testing.md) |
| Docker / compose / сервер | [`manuals/docker.md`](manuals/docker.md) |
| LLM | [`manuals/llm.md`](manuals/llm.md) |
| Облачный цикл (research handoff) | [`manuals/cloud_flow.md`](manuals/cloud_flow.md) |
| Контракты для агентов | [`agent_docs/contracts/index.md`](agent_docs/contracts/index.md) |
| План / roadmap | [`agent_docs/plans/draft_demo_roadmap.md`](agent_docs/plans/draft_demo_roadmap.md) |
| Прогресс этапов | [`agent_docs/progress/`](agent_docs/progress/) · журнал [`log.md`](agent_docs/progress/log.md) |
| Открытые тикеты | [`agent_docs/plans/`](agent_docs/plans/) (`ticket_*.md`, статус в шапке) |

Исследование стека зафиксировано; архив (read-only): `docs/research_results/`.

## Быстрый старт

Локально (без Docker):

```bash
uv sync
export JOB_IP_SALT=local-dev-salt   # обязателен; не коммитить .env
uv run transcriber healthcheck
uv run transcriber serve --reload   # http://127.0.0.1:8000/
```

Профиль и ключи: [`manuals/configuration_guide.md`](manuals/configuration_guide.md).  
Образ / compose / секреты volume: [`manuals/docker.md`](manuals/docker.md).

## Стек (демо)

Silero VAD → WeSpeaker ONNX → GigaAM `v3_rnnt` → packing C (`rubert-tiny2`) → LLM (в `demo` — Qwen). Шумодав не используем. Подробности — в мануалах и `config/`.

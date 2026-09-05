# Настройка YAML (профили)

[NEW] Как выбрать профиль и что править человеку. Полные схемы ключей — в контрактах Planner (`agent_docs/contracts/config_profiles.md`), сюда их не копируем.

## Какой файл за что отвечает

| Файл | Профиль | Когда |
|---|---|---|
| `config/demo.yaml` | `demo` | облачная демка, лимиты, Gemini API |
| `config/dev.yaml` | `dev` | локальная разработка, local LLM, без жёстких лимитов |
| `config/prod.yaml` | `prod` | контур заказчика (часть движков пока заглушки) |

Загрузка: `src/transcriber/config/loader.py` читает `config/{profile}.yaml` из cwd или корня репо.

## Как выбрать профиль

```bash
export APP_PROFILE=demo    # по умолчанию, если не задано
export APP_PROFILE=dev
export APP_PROFILE=prod
```

Либо флаг CLI там, где есть `--profile` / `-p` (`plan`, `convert-legacy`, `healthcheck`).

Обязательные секреты/соль (не в YAML):

| Переменная | Зачем |
|---|---|
| `JOB_IP_SALT` | хэш IP для лимитов; без неё `/healthz` и `healthcheck` падают |
| `GEMINI_API_KEY` | только когда `llm.provider: gemini` реально вызывается (с D3 / демка) |
| `HF_TOKEN` | загрузка моделей (с D1), не в yaml |

`.env` в приложение не читаем — только окружение / Cursor secrets.

## Что править для типичных ситуаций

| Ситуация | Куда смотреть |
|---|---|
| Укоротить лимит аудио демки | `config/demo.yaml` → `audio.max_minutes` |
| Лимит запросов с IP / TTL результата | `demo.yaml` → `limits.*` |
| Сменить облачную LLM | `demo.yaml` → `llm.provider` / `model` / `api_key_env` |
| Локальный Qwen вместо API | `APP_PROFILE=dev` (там `llm.mode: local`, `local_llama`) |
| Включить late chunking / pyannote | только `dev`/`prod` yaml + реальная реализация; в `demo` недоступно |
| Путь хранения job-артефактов | `app.storage_root` (по умолчанию `./var`) |

Не хардкодьте пороги в `src/` — меняйте YAML.

## Секции внутри файла (обзор)

Одинаковая структура во всех профилях: `app`, `audio`, `vad`, `diarization`, `asr`, `correction`, `chunking`, `llm`, `limits`, `ui`.  
Значения по умолчанию для демки: ~15 минут аудио, Gemini, 1 задача/IP/сутки, UI Jinja (веб появится на D4).

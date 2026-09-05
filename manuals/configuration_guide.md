# Настройка YAML (профили)

[NEW] Как выбрать профиль и что править человеку. Полные схемы ключей — в контрактах Planner (`agent_docs/contracts/config_profiles.md`), сюда их не копируем.

## Какой файл за что отвечает

| Путь | Роль |
|---|---|
| `config/base.yaml` | общие дефолты (speech / chunking / runtime) |
| `config/profiles/demo.yaml` | дельты публичной демки |
| `config/profiles/dev.yaml` | дельты разработки |
| `config/profiles/prod.yaml` | дельты боевого контура |

Загрузка: `load_config` делает deep-merge `base ← profiles/{APP_PROFILE}.yaml`, затем валидирует `AppConfig`.

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
| Укоротить лимит аудио демки | `profiles/demo.yaml` или `base` → `audio.max_minutes` |
| Пороги Silero VAD | `base.yaml` → `vad.threshold` / `neg_threshold` / `min_*` |
| Лимит запросов с IP / TTL | `profiles/demo.yaml` → `limits.*` |
| Сменить облачную LLM | `profiles/demo.yaml` → `llm.*` |
| Локальный Qwen вместо API | `APP_PROFILE=dev` |
| Включить late chunking / pyannote | `dev`/`prod` overlay + реальная реализация |
| Путь хранения job-артефактов | `app.storage_root` (по умолчанию `./var`) |

Не хардкодьте пороги в `src/` — меняйте YAML.

## Секции внутри файла (обзор)

Одинаковая структура: `app`, `audio` (+ `gain`), `vad`, `diarization` (+ `merge` / `embed`), `asr`, `correction`, `chunking`, `llm`, `limits`, `ui`.

# Настройка YAML (профили)

[NEW] Как выбрать профиль и что править человеку. Полные схемы ключей — в контрактах Planner (`agent_docs/contracts/config_profiles.md`), сюда их не копируем.

## Какой файл за что отвечает

| Путь | Роль |
|---|---|
| `config/base.yaml` | общие дефолты (speech / chunking / runtime) |
| `config/base_llm.yaml` | LLM: mode, backend, backends, tasks (с D3) |
| `config/llm_extra/` | опционально: уникальные ключи одного API |
| `config/profiles/demo.yaml` | дельты публичной демки |
| `config/profiles/dev.yaml` | дельты разработки |
| `config/profiles/prod.yaml` | дельты боевого контура |

Загрузка: `load_config` делает deep-merge `base.yaml` ← `base_llm.yaml` ← `profiles/{profile}.yaml`, затем валидирует `AppConfig`.

## Как выбрать профиль

Профиль **не** хранится в `.env` (там только секреты). Порядок:

1. флаг CLI `--profile` / `-p`
2. переменная процесса `APP_PROFILE` (systemd, `export`, `transcriber serve -p`) — не из `.env`
3. `config/base.yaml` → `app.profile` (**сейчас `demo`**)

```yaml
# config/base.yaml
app:
  profile: demo   # demo | dev | prod
```

Обязательные секреты/соль (не в YAML):

| Переменная | Зачем |
|---|---|
| `JOB_IP_SALT` | хэш IP для лимитов; без неё `/healthz`, `healthcheck` и `serve` падают |
| `QWEN_API_KEY` | активный backend профиля **demo** (`llm.backend: qwen`) |
| `GEMINI_API_KEY` | только если `llm.backend: gemini` (`base_llm.yaml`, оверлеи `dev`/`prod`) |
| `NVIDIA_API_KEY` | только если `llm.backend: nvidia` |
| `HF_TOKEN` | загрузка моделей (с D1), не в yaml |

Имена переменных ключей LLM задаются в `config/base_llm.yaml` (`api_key_env`). Значения — окружение или `.env` в корне репо (не коммитить). `load_config` подхватывает `.env` сам, **не** перезаписывая уже заданные переменные. Значения в логи не пишутся. Подробно: [`llm.md`](llm.md).

## Что править для типичных ситуаций

| Ситуация | Куда смотреть |
|---|---|
| Укоротить / удлинить лимит аудио демки | `audio.max_minutes` в `config/base.yaml` или profile overlay. Длиннее лимита → предупреждение и обрезка (не отказ); oversize файла → отказ |
| Лимит кнопки саммари в UI | `ui.summary_max_calls` (demo = 2); не путать с `llm.max_calls_per_job` (полный extract+report) |
| Правки / плеер в UI | `ui.allow_editing`, `ui.allow_player` |
| Пороги Silero VAD | `base.yaml` → `vad.threshold` / `neg_threshold` / `min_*` |
| VAD preprocess (опционально) | `base.yaml` → `audio.vad_preprocess` (по умолчанию **выкл.**; C3 dynaudnorm оставлен только как строка-заготовка) |
| Склейка фраз / absorb спикеров | `base.yaml` → `diarization.merge` (`vad_premerge_gap_sec`, `same_speaker_gap_sec`, `absorb_turn_shorter_than_sec`) |
| Per-turn gain перед GigaAM | `base.yaml` → `audio.asr_per_turn_gain` + `audio.gain.*` |
| Лимит запросов с IP / TTL | `profiles/demo.yaml` → `limits.*` |
| Сменить облачную LLM | overlay профиля (`profiles/demo.yaml` → `llm.backend`) или `base_llm.yaml`; ключ в `.env`; см. [`llm.md`](llm.md) |
| Другая модель / URL API | `llm.backends.<name>.model` / `base_url` |
| Длиннее саммари | `llm.tasks.meeting_insights.report.max_tokens` |
| Новый текст промпта | новый файл в `src/transcriber/llm/prompts/<таска>/` + путь в yaml |
| Локальный GGUF | пока нельзя (`llm.mode: local` зарезервирован) |
| Включить late chunking / pyannote | `dev`/`prod` overlay + реальная реализация |
| Путь хранения job-артефактов | `app.storage_root` (по умолчанию `./var`) |

Не хардкодьте пороги в `src/` — меняйте YAML.

## Секции внутри файла (обзор)

Одинаковая структура: `app`, `audio`, `vad`, `diarization`, `asr`, `correction`, `chunking`, `llm` (с D3 — в `base_llm.yaml`), `limits`, `ui`.

Актуальные дефолты speech после D1 Silero T2: `vad.threshold=0.45`, `neg_threshold=0.30`, `min_speech_ms=200`, `min_silence_ms=350`, `merge.vad_premerge_gap_sec=0.5`, `same_speaker_gap_sec=0.3`, `absorb_turn_shorter_than_sec=1.0`, `audio.vad_preprocess.enabled=false`. Источник правды — `config/base.yaml`, не этот абзац.

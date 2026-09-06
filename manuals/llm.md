# LLM: конфиги, бэкенды, промпты, схемы

Как человеку сменить модель, промпт или лимит токенов **без правки Python**.  
Контракт (для агентов): [`agent_docs/contracts/llm/`](../agent_docs/contracts/llm/), план обёртки: [`agent_docs/plans/draft_llm_wrapper.md`](../agent_docs/plans/draft_llm_wrapper.md).

Секреты в yaml **не пишем** — только имя переменной (`api_key_env`). Значение берётся из окружения или `.env` (файл в git не коммитим).

---

## 1. Какие файлы за что отвечают

```text
config/base.yaml                 # речь, чанкинг, лимиты — не трогать ради смены модели
config/base_llm.yaml             # всё про LLM: mode, backend, backends, tasks
config/profiles/demo.yaml        # обычно только llm.backend: gemini и llm.mode: api
config/llm_extra/*.yaml          # редко: ключи, которые есть у одного API и нет у другого
src/transcriber/llm/prompts/     # тексты промптов, папка = таска
src/transcriber/llm/schemas/     # JSON Schema ответа, отдельно от промптов
```

Загрузка: `base.yaml` ← `base_llm.yaml` ← `profiles/{APP_PROFILE}.yaml`.

Эталон содержимого `base_llm.yaml` (копируется в `config/` на этапе D3):  
[`agent_docs/contracts/llm/base_llm.yaml`](../agent_docs/contracts/llm/base_llm.yaml).

---

## 2. Режим и какой бэкенд активен

```yaml
llm:
  mode: api          # api | local   (local зарезервирован, в demo не включаем)
  backend: gemini    # gemini | nvidia | qwen
```

Сменить провайдера — одна строка `backend:` (и ключ этого бэкенда в окружении). Промпты те же.

| backend | Переменная ключа | Клиент | `base_url` |
|---|---|---|---|
| `gemini` | `GEMINI_API_KEY` | Google GenAI | `null` (не OpenAI-совместимый хост) |
| `nvidia` | `NVIDIA_API_KEY` | `openai_compat` | `https://integrate.api.nvidia.com/v1` |
| `qwen` | `QWEN_API_KEY` | `openai_compat` | DashScope compatible-mode (см. yaml) |

Нужен только ключ **активного** бэкенда. Остальные могут быть пустыми.

Локальный GGUF / llama.cpp: `mode: local` появится позже. Пока не ставим и не качаем веса.

---

## 3. Блок `backends` (модель + URL + ключ)

Общие поля у каждого имени:

```yaml
backends:
  gemini:
    client: gemini
    api_key_env: GEMINI_API_KEY
    model: gemini-2.5-flash
    base_url: null
    extra_config: null
  nvidia:
    client: openai_compat
    api_key_env: NVIDIA_API_KEY
    model: meta/llama-3.1-70b-instruct
    base_url: https://integrate.api.nvidia.com/v1
    extra_config: null
  qwen:
    client: openai_compat
    api_key_env: QWEN_API_KEY
    model: qwen-plus
    base_url: https://dashscope-intl.aliyuncs.com/compatible-mode/v1
    extra_config: null
```

- Сменить модель NVIDIA → правьте `backends.nvidia.model`, не код.
- Другой хост Qwen → правьте `backends.qwen.base_url`.
- `extra_config` — **не** для url/модели/промпта. Только уникальные поля API (есть у Gemini, нет у OpenAI-compat, или наоборот). Если уникального нет — `null`.

Пример уникального оверлея (не подключён по умолчанию):  
[`agent_docs/contracts/llm/extra/no_temperature.yaml`](../agent_docs/contracts/llm/extra/no_temperature.yaml) — `temperature: null` (не слать параметр) + замена вроде `reasoning_effort`. Подключение:

```yaml
backends:
  nvidia:
    extra_config: llm_extra/no_temperature.yaml
```

---

## 4. Общие параметры вызова (`base_llm`) и таски

```yaml
base_llm:
  temperature: 0.2
  max_tokens: 2048
  response_format: json
  timeout_sec: 60
```

Таска может **переопределить** `max_tokens` / `temperature` / `response_format`. У таски **нет** `extra_config` — уникальные ключи всегда с бэкенда.

Имя таски = папка промптов. Сначала заголовки глав, потом инсайты встречи.

Вложенность extract/report внутри `meeting_insights` — удобный вариант «одна таска, два вызова». Так же законно вынести report соседней таской; важно, чтобы путь к файлу промпта был ясен.

```yaml
tasks:
  chapter_titles:
    prompt: prompts/chapter_titles/v1.md
    schema: schemas/chapter_title.json
    max_tokens: 1024
  meeting_insights:
    extract:
      prompt: prompts/meeting_insights/v1_extract.md
      schema: schemas/chapter_extract.json
      max_tokens: 2048
    report:
      prompt: prompts/meeting_insights/v1_report.md
      schema: schemas/meeting_report.json
      max_tokens: 3072    # длиннее саммари — поднимите это число
```

Слияние на один вызов: `base_llm` → поля бэкенда (`base_url`, модель) → `extra_config` бэкенда → поля шага таски.  
YAML `null` у числа = не передавать параметр в API.

---

## 5. Промпты и схемы — разные деревья

```text
src/transcriber/llm/prompts/
  chapter_titles/v1.md
  meeting_insights/v1_extract.md
  meeting_insights/v1_report.md
  qa_session/                 # будущая таска, пока пусто
src/transcriber/llm/schemas/
  chapter_title.json
  chapter_extract.json
  meeting_report.json
```

Правила:

1. Папка = таска. Файл = версия: `v1.md`, `v1_extract.md`, позже `v2_short.md` / `v2_reach.md`.
2. Схема **не** лежит рядом с промптом. Путь — в yaml шага (`schema:`).
3. Текст frozen-файла не правят in-place: новый файл + смена пути в yaml.
4. Промпт не знает провайдера. `/no_think`, JSON MIME, `base_url` — клиент или бэкенд.
5. Модель не выдаёт часы: только `segment_id` / `chapter_id`. Код копирует `start`/`end`/`speaker` из транскрипта.

### Как добавить версию саммари

1. Скопировать `prompts/meeting_insights/v1_report.md` → `v2_reach.md`, править копию.
2. В `base_llm.yaml`:

```yaml
meeting_insights:
  report:
    prompt: prompts/meeting_insights/v2_reach.md
    schema: schemas/meeting_report.json   # та же схема, если JSON не менялся
    max_tokens: 4096
```

3. Если формат JSON ответа другой — новый файл в `schemas/` и новый путь `schema:`.

### Как завести новую таску (например Q&A)

1. Папка `prompts/qa_session/v1.md` + при необходимости `schemas/qa_session.json`.
2. Блок в `tasks:`:

```yaml
tasks:
  qa_session:
    prompt: prompts/qa_session/v1.md
    schema: schemas/qa_session.json
    max_tokens: 2048
```

3. Шаг пайплайна, который читает `cfg.llm.tasks.qa_session` — отдельно, когда появится продукт.

---

## 6. Типичные правки

| Хочу | Куда |
|---|---|
| Gemini → NVIDIA | `llm.backend: nvidia` + `NVIDIA_API_KEY` в окружении |
| Другая модель Qwen | `backends.qwen.model` |
| Другой endpoint Qwen | `backends.qwen.base_url` |
| Длиннее финальный отчёт | `tasks.meeting_insights.report.max_tokens` |
| Новый текст extract | новый файл в `prompts/meeting_insights/` + путь в yaml |
| Параметр только у Gemini | `backends.gemini.extra_config: llm_extra/….yaml` |
| Локальный инференс | пока нельзя; ждать `mode: local` |

Не хардкодьте модель и промпт в `src/`.

---

## 7. Секреты и `.env`

В yaml: `api_key_env: GEMINI_API_KEY`.  
В `.env` (локально) или в дашборде Cloud Agent:

```text
GEMINI_API_KEY=…
NVIDIA_API_KEY=…    # если backend: nvidia
QWEN_API_KEY=…      # если backend: qwen
```

`load_config` вызывает `python-dotenv` для файла `.env` в cwd или рядом с `config/` (`override=false`). Приложение читает значение по имени. В логи пишется имя переменной, не значение. `.env` не коммитить. Агентам запрещено открывать `.env` и печатать секреты.

`backends.*.extra_config` читается при вызове (`base_llm ← extra ← task`). Пример: `config/llm_extra/no_temperature.yaml`.

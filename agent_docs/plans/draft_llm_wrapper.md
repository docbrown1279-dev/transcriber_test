# LLM wrapper (D3, revision 3)

**Status:** PLAN_DRAFT, ждёт ✅.
**Зачем:** один yaml на LLM; `backends` с `base_url`; промпты по таскам (`chapter_titles`, затем `meeting_insights`). Локальный инференс в demo не включаем.
**Связано:** [`draft_D3_scope.md`](draft_D3_scope.md), примеры [`../contracts/llm/`](../contracts/llm/).

---

## 1. Режим и провайдеры

| Режим `llm.mode` | Что это | Demo D3 |
|---|---|---|
| `api` | HTTP к внешней модели | **единственный рабочий** |
| `local` | локальный рантайм (llama.cpp и т.п.) | **зарезервирован**, не реализуем, не ставим GGUF |

Облако = API. По умолчанию Gemini. Смена бэкенда — `llm.backend`, не правка кода.

| `backend` | `api_key_env` | Клиент | Модель в примере | `base_url` |
|---|---|---|---|---|
| `gemini` | `GEMINI_API_KEY` | `gemini` | `gemini-2.5-flash` | `null` (нативный SDK) |
| `nvidia` | `NVIDIA_API_KEY` | `openai_compat` | `meta/llama-3.1-70b-instruct` | NIM |
| `qwen` | `QWEN_API_KEY` | `openai_compat` | `qwen-plus` | DashScope compatible-mode |

Значение секрета — из окружения / `.env` по **имени** из yaml. Агент `.env` не открывает.

`local_llama` — заглушка реестра до `mode: local`. На D3 не кодируем.

---

## 2. Один файл `base_llm.yaml`

Загрузка: `config/base.yaml` → **`config/base_llm.yaml`** → `config/profiles/{profile}.yaml`.

Пример: [`../contracts/llm/base_llm.yaml`](../contracts/llm/base_llm.yaml).

### Поля

**Корень `llm`:** `mode`, `backend`, `max_calls_per_job`.

**`base_llm`** — общие параметры вызова: `temperature`, `max_tokens`, `response_format`, `timeout_sec`. Без `extra_config`.

**`backends.<name>`:**

- `client`, `api_key_env`, `model`
- `base_url` — хост OpenAI-compat; у Gemini `null`
- `extra_config` — путь или `null`; **только** ключи, которых нет у другого клиента (Gemini-only vs openai_compat и наоборот). Не сюда: url, имя ключа, модель, промпт, схема, max_tokens

**`tasks.<task>`** — имя = папка промптов. Сначала `chapter_titles`, затем `meeting_insights` (внутри два вызова: extract и report).

На задаче: `prompt`, `schema`, и при необходимости оверлей общих параметров (`max_tokens`, `temperature`, `response_format`). **`extra_config` на задаче нет** — уникальные ключи API берутся с активного бэкенда.

Слияние вызова: `base_llm` ← поля бэкенда (`base_url`, …) ← `backends.*.extra_config` ← поля шага задачи (`max_tokens` и т.п.).  
YAML `null` у числового параметра = не передавать в API.

---

## 3. Промпты по таскам, схемы отдельно

```text
src/transcriber/llm/
  prompts/
    chapter_titles/          # таска: заголовки глав (нужна до insights)
      v1.md
    meeting_insights/        # таска: extract по главам + один report
      v1_extract.md
      v1_report.md           # позже: v2_short.md, v2_reach.md
    qa_session/              # будущая таска, в D3 не вызывается
      README.md
  schemas/
    chapter_title.json
    chapter_extract.json
    meeting_report.json
```

1. Папка = таска. Файл = версия (`v1.md`, `v1_extract.md`, `v2_reach.md`).
2. Схема — отдельное дерево; путь в yaml шага.
3. Смена текста = новый файл + смена пути. Frozen не правим in-place.
4. Тело provider-neutral. `base_url` и уникальные API-ключи — бэкенд / extra_config бэкенда.
5. Плейсхолдеры `{{name}}` у extract/report; хвост `{{…}}` после render — ошибка.
6. Модель не выдаёт время — только `segment_id` / `chapter_id`.

D2 `title_p1_v1.md` в пакете остаётся, пока titles не переключат путь на `prompts/chapter_titles/v1.md`.

---

## 4. Порт

```python
class LlmClient(Protocol):
    name: str
    def complete(
        self,
        prompt: str,
        *,
        prompt_id: str,
        max_tokens: int | None,
        temperature: float | None,
        json_schema: dict | None,
        extra: dict[str, object] | None = None,
    ) -> LlmResponse: ...
```

`None` — поле не уходит в API. `extra` — только содержимое backend `extra_config`. `base_url` передаётся при сборке клиента, не через extra задачи.

Фабрика: `backends[backend].client` + ключ + модель + `base_url`. Реестр: `gemini` (есть), `openai_compat` (реализовать), `local_llama` (заглушка).

---

## 5. Слой задач пайплайна

`chapter_titles` уже есть в D2. D3: `meeting_insights.extract` по главам → `meeting_insights.report` один раз → `report.md` без LLM. Clock-gate после hydration.

---

## 6. Секреты

В yaml только `api_key_env`. Нужен ключ активного backend. Шлюз D3 по умолчанию — Gemini.

---

## 7. Не делаем на D3

- llama.cpp / GGUF
- отдельный yaml на каждую модель
- schema-файл рядом с каждым промптом
- extra_config на задаче
- фильтр «нет инсайтов»


# Черновик архитектуры приложения (Фаза A)

**Статус:** draft, ждёт ✅.
**Связано:** [roadmap](draft_demo_roadmap.md), контракты [артефактов](../contracts/pipeline_artifacts.md), [интерфейсов](../contracts/module_interfaces.md), [конфигов](../contracts/config_profiles.md).

---

## 1. Принципы

1. **Файловые артефакты между этапами.** Каждый шаг пайплайна читает и пишет JSON в каталоге задачи. Так этап разработки можно тестировать и запускать изолированно, а облачные агенты D2/D3/D4 работают на фикстурах, не гоняя ASR.
2. **Один порт на каждый сменный компонент.** Всё, что в ТЗ §5 различается между `dev`/`demo`/`prod`, живёт за `Protocol` и создаётся фабрикой по конфигу. Профиль не выбирается кодом «if profile == …» внутри логики.
3. **Заглушки вместо ветвлений.** Компоненты `prod` регистрируются сразу, но в демке бросают `ComponentUnavailableError` с текстом «включается в профиле prod». Их наличие проверяется тестами реестра.
4. **Никаких магических чисел.** Пороги (0,70 чанкинга, 25 с сегмента, −30 dBFS, 0,3/1,0 с склейки, лимиты) — только из конфига.
5. **LLM не источник времени.** Таймкоды копируются из ASR-сегментов; любой ответ модели проходит clock-gate.

## 2. Дерево кода

```
pyproject.toml                # uv, зависимости профиля demo + dev-группа
config/
  demo.yaml  dev.yaml  prod.yaml
src/transcriber/
  config/        loader.py, schema.py        # pydantic-модели конфига, профиль из env
  models/        artifacts.py                # pydantic-модели всех JSON-артефактов
  audio/         normalize.py, gain.py       # ffmpeg, RMS/peak через astats
  vad/           base.py, silero.py, ten.py  # ten = опциональный fallback
  diarization/   base.py, wespeaker.py, pyannote_stub.py
  asr/           base.py, gigaam.py, splitter.py, holes.py
  correction/    base.py, suggester.py, dictionaries/
  chunking/      base.py, packing_c.py, embeddings.py, late_chunking_stub.py
  llm/           base.py, gemini.py, local_llama.py, openai_compat_stub.py, prompts/
  insights/      titles.py, extract.py, report.py, clock_gate.py
  pipeline/      orchestrator.py, steps.py, artifacts.py, events.py
  jobs/          store.py, queue.py, ttl.py
  web/           app.py, routes.py, limits.py, templates/, static/
  quality/       ru_ratio.py, chapter_metrics.py, checks.py   # шлюзы как код, не как ручная проверка
  cli.py                                     # запуск пайплайна без веба (dev/CI)
tests/
  unit/  contract/  integration/  e2e/  fixtures/
```

## 3. Пайплайн

```
upload → normalize → vad → diarize → merge_turns → asr → correction_suggest
       → chunk_c → titles → insights_extract → report → result
```

Шаги оформлены однотипно: `run(ctx, config) -> Artifact`, регистрируются в `orchestrator` списком, каждый умеет «пропустить, если артефакт уже есть» (перезапуск задачи без повторного ASR). Прогресс — события `StageEvent(stage, status, pct, message)` в `jobs/store`, откуда их читает страница прогресса.

Порядок склейки turn'ов и резки для ASR берётся из 1e/1f дословно: gap ≤0,3 с того же спикера объединяем, turn <1,0 с поглощаем соседом, дыры ≥0,5 с фиксируем в артефакте, сегменты >25 с режем только по времени.

## 4. Порты и заглушки

| Порт | `demo` | Заглушка для `prod`/`dev` |
|---|---|---|
| `VoiceActivityDetector` | `silero` | `ten` (флаг, лицензия), `disabled` |
| `Diarizer` | `wespeaker_onnx` | `pyannote31` |
| `AsrEngine` | `gigaam_v3_rnnt` | `gigaam_e2e`, `whisper_*` (не реализуем) |
| `TermSuggester` | `dictionary_suggest` с пустым словарём | доменные словари, авто-Левенштейн, обучение |
| `Chunker` | `packing_c` | `late_chunking_jina`, `hybrid_c_then_d` |
| `EmbeddingBackend` | `rubert_tiny2` | `bge_small_onnx`, `jina_v3` |
| `LlmClient` | `gemini` (облако и демка) | `local_llama` — реальная реализация для локальных прогонов (D3); `openai_compat` — заглушка |
| `Exporter` | `json`, `markdown` | `pdf` |
| UI-возможности | просмотр результата | `allow_editing`, `allow_player` — флаги конфига, шаблоны-заготовки |

Все заглушки — один паттерн: реализация порта, регистрация в фабрике, `raise ComponentUnavailableError(component, profile, hint)`. Никаких `pass` и никаких «тихих» фоллбэков на другой компонент.

## 5. Веб-слой демки

- FastAPI + Jinja2, три страницы (`/`, `/jobs/{id}`, `/jobs/{id}/result`) + `/jobs/{id}/download`, `/healthz`, `/metrics` (опционально, простой текст).
- Прогресс: polling `GET /jobs/{id}/events` (JSON) и SSE как надстройка — polling обязателен, SSE опционален (ТЗ допускает оба).
- Очередь: один процесс-воркер, `max_concurrent_jobs: 1`; вторая задача отвергается с понятным сообщением.
- Лимиты: `requests_per_ip_per_day`, `max_file_size_mb`, `max_minutes`, `result_ttl_hours` — всё из конфига; учёт по IP в sqlite/файле состояния, чтобы демка не требовала внешней БД.
- Приватность: загруженный файл и артефакты удаляются TTL-уборкой; в логах — только id задачи и метрики, без текста и без ключей.

## 6. Ресурсы и процессы (2–3 vCPU / 7–8 ГБ)

| Этап | Где считается | Ожидание по 1e/1f (масштаб на 15 мин) |
|---|---|---|
| VAD + диаризация | отдельный процесс, ONNX, без torch | < 1 мин, peak RSS ~250–400 МиБ |
| ASR GigaAM | отдельный процесс, CPU torch | RTF ≈0,035 на 4 vCPU → ориентир 1–3 мин на 2 vCPU |
| Эмбеддинги + чанкинг | процесс воркера | секунды |
| LLM (API) | сеть | 12–15 вызовов, десятки секунд (3c: 13 вызовов ~25 с) |

Ключевое требование: **torch живёт только в ASR-подпроцессе** — иначе веб-процесс держит лишние гигабайты всё время жизни демки. Реальные числа снимаются в D1 и D5, оценки выше — ориентиры исследования, не обещания.

## 7. Конфигурация и секреты

`config/{profile}.yaml` повторяет структуру ТЗ §6 без переименований; профиль выбирается `APP_PROFILE`. Секреты — только из окружения (`HF_TOKEN`, `GEMINI_API_KEY`, `JOB_IP_SALT`), никогда из yaml и никогда в логах. `.env` не читаем и не коммитим; для облака ключи задаются в дашборде Cursor, `QWEN_API_KEY` в облако не передаётся (локальная модель ключа не требует).

## 8. Что сознательно не делаем в демке

Шумоподавление, late chunking, ручное редактирование, плеер, диаризация pyannote, PDF-экспорт, дообучение словарей, повторный прогон полного 24-минутного файла в облаке. Локальная LLM в демке не работает (2 vCPU не хватит), но код для неё есть — она включается профилем `dev` на машине человека.

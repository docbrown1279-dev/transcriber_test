# Ручная проверка (smoke)

Инструкции для человека после облачного этапа. Автошлюзы (gate) — в `agent_docs/reports/`; здесь только то, что стоит прогнать локально глазами/руками.

Перед любым smoke:

```bash
cd /work/speech_rec_test   # корень репо
export PATH="$HOME/.local/bin:$PATH"   # если gh ставили в ~/.local
uv sync
export JOB_IP_SALT=local-dev-salt      # обязателен для healthcheck /healthz
```

Профиль по умолчанию — `demo` (`config/base.yaml` → `app.profile`). Настройка профилей: [`configuration_guide.md`](configuration_guide.md). Облачный цикл: [`cloud_flow.md`](cloud_flow.md).

---

## Stage D0 — каркас [NEW]

**Смысл этапа:** скелет приложения без ASR/LLM. Человеку не нужно слушать аудио и читать транскрипт.

**Критерий выхода:** gate G0 = PASS (уже в `agent_docs/reports/D0/gate_D0.md`); локальный smoke ниже зелёный.

### Smoke

```bash
uv run transcriber healthcheck
uv run transcriber probe-audio cloud_in/inputs/audio/test_voice.m4a
uv run transcriber convert-legacy \
  cloud_in/inputs/artifacts/baseline_transformers.json \
  /tmp/d0_transcript.json
uv run transcriber validate /tmp/d0_transcript.json
mkdir -p /tmp/d0_job && cp /tmp/d0_transcript.json /tmp/d0_job/transcript.json
uv run transcriber plan --job /tmp/d0_job
uv run pytest tests/ -v
```

Ожидание:

| Команда | Ожидание |
|---|---|
| `healthcheck` | exit 0; есть ffmpeg/ffprobe; при наличии клипа — duration ~83 s |
| `probe-audio` | JSON с duration ≈ 83 |
| `validate` | exit 0 на сконвертированном транскрипте |
| `plan` | 9 стадий; ранние могут быть `done`/`pending`, тяжёлые — `unavailable` / not implemented |
| `pytest` | все зелёные (без сети; тесты с `requires_inputs` — если есть `cloud_in/inputs/`) |

Опционально веб:

```bash
uv run uvicorn transcriber.web.app:app --host 127.0.0.1 --port 8000
# GET http://127.0.0.1:8000/healthz → 200
```

### Человеческий шлюз D0

- [ ] Открыть `agent_docs/reports/D0/gate_D0.md` — Verdict PASS  
- [ ] Smoke-команды выше без ошибок  
- [ ] PR/merge в `main` (D0 уже влит как PR #16)  

**Не требуется на D0:** слушать `test_voice.m4a`, оценивать качество речи, править промпты LLM.

---

## Порядок после D0

```text
D0 CLOSED → D1 (G1 + HUMAN_GATE) → D2 → D3 → D4 локальный UI (HUMAN_GATE в браузере) → D5
```

D1–D3 уже в `main` с `HUMAN_GATE: PASS`. D4 влит в `main`; человеческий шлюз — прогон демки в браузере (раздел ниже).

---

## Stage D1 — голос → транскрипт

**Смысл этапа:** нормализация, VAD, диаризация, ASR, suggestions (пустой словарь). Облако гоняет **полную** запись `voice_002.m4a` и автопроверки этапа (G1); человек слушает локально после pull.

**Критерий выхода:** `agent_docs/reports/D1/gate_D1.md` = PASS/PASS_WITH_WARNINGS **и** `HUMAN_GATE: PASS` в progress.

### Локальная сверка с gold (`eval/d1`)

Актуальный полный hyp после Silero T2: **`data/voice_002/`** — только `transcript.json` + `transcript.md` (gitignored). Полный job (wav / speech / turns): **`var/jobs/voice_002_t2/`**. Старый C3+agg: `.trash/voice_002_c3_agg/`.

```bash
# полный прогон (~25 мин аудио) до suggestions — в var, не в data/
export HF_HUB_OFFLINE=1
.venv/bin/python -m transcriber.cli run \
  -j var/jobs/voice_002_t2 -a "data/voice 002.m4a" -p demo -u correction_suggest
cp var/jobs/voice_002_t2/transcript.json data/voice_002/

# eval-скрипт по умолчанию читает results/d1
mkdir -p results/d1
cp data/voice_002/transcript.json var/jobs/voice_002_t2/{turns,speech,audio}.json results/d1/
EVAL_D1_ATTEMPT=6 python3 scripts/eval_d1_manual.py
```

Проверки пишутся в `eval/d1/{N}/` (`transcript_diff.md`, summary). Спикеров сопоставляет человек: кластеры WeSpeaker и буквы A/B/C в gold **не** совпадают 1:1.

### Человеческий шлюз D1

- [ ] Gate G1 в отчёте — PASS или PASS_WITH_WARNINGS  
- [ ] Просмотреть `eval/d1/transcript_diff.md`, послушать `eval/d1/voice/…`  
- [ ] Опционально: WER/CER vs `eval/`  
- [ ] Записать в `agent_docs/progress/stage_D1.md`: `HUMAN_GATE: PASS|FAIL` + одна фраза  

**Не делать на D1:** главы, LLM-отчёт, веб-загрузка (D2–D4).

---

## Stage D2 — главы и названия

Оглавление на полном транскрипте. Автошлюз G2; человек читает TOC как ориентир.

Критерий: `HUMAN_GATE: PASS` в `agent_docs/progress/stage_D2.md` (уже есть).

---

## Stage D3 — инсайты и отчёт LLM

**Смысл:** extract по главам → один report → `report.md` (рендер JSON, не второй ответ модели). Облако гоняет Gemini на packed `transcript.json` + `chapters.json`. Настройка моделей и промптов: [`llm.md`](llm.md).

**Критерий выхода:** `gate_D3.md` PASS/PASS_WITH_WARNINGS **и** `HUMAN_GATE: PASS` в `stage_D3.md`.

### Smoke после pull

```bash
uv run transcriber quality check-insights \
  cloud_out/artifacts/voice_002/insights.json \
  --chapters cloud_in/inputs/artifacts/voice_002/chapters.json \
  --transcript cloud_in/inputs/artifacts/voice_002/transcript.json
# либо пути после ingest: agent_docs/reports/D3/ и data/voice_002/
```

### Человеческий шлюз D3

- [ ] Прочитать `report.md` целиком на фоне `data/voice_002/transcript.md` (и аудио при желании)
- [ ] Нет выдуманных поручений, цифр, ФИО; таймкоды выглядят как из глав
- [ ] Это черновик протокола (`draft_warning`), не итоговый документ
- [ ] Записать `HUMAN_GATE: PASS|FAIL` + одна фраза в `stage_D3.md`

Смена модели для локальной сверки: `llm.backend` в `config/base_llm.yaml` (NVIDIA/Qwen API), те же промпты. Локальный GGUF на D3 не включаем.

**Не делать на D3:** веб-загрузка (это уже D4), правка транскрипта, новый чанкинг.

---

## Stage D4 — демо UI (локально)

**Смысл этапа:** Jinja-демка без cloud handoff. Загрузка файла → прогресс → оглавление глав → страница главы. Воркер веб-задачи идёт **до стадии `titles`** (названия глав). Полный extract+report пайплайна **не** запускается сам: саммари — кнопка на оглавлении.

**Критерий выхода:** локальный smoke + человеческий прогон в браузере; `HUMAN_GATE` записать в `agent_docs/progress/stage_D4.md`. Playwright нет.

### Запуск

Нужны `JOB_IP_SALT` и `QWEN_API_KEY` (профиль `demo` → `llm.backend: qwen`). Профиль не класть в `.env`.

```bash
export JOB_IP_SALT=local-dev-salt
uv run transcriber serve --reload
# http://127.0.0.1:8000/
```

Либо `uv run uvicorn transcriber.web.app:app --host 127.0.0.1 --port 8000 --reload`.

### Поток в браузере

```text
/                        загрузка файла (поле URL — только классификация youtube/yandex/unknown, файл всё равно нужен)
→ /jobs/{id}             прогресс: полоса + прошедшее время
→ /jobs/{id}/result      оглавление (id глав C00…) + плеер
→ /jobs/{id}/chapters/{cid}  текст главы, правки, prev/next
```

Старые HTML-макеты: `/stubs/upload`, `/stubs/result`, `/stubs/chapter`.

### Лимиты и ошибки

- `audio.max_minutes=30`: длиннее → предупреждение и обрезка, не отказ.
- Слишком большой файл (`audio.max_file_size_mb`) → отказ.
- Лимит запросов с IP/сутки **не** действует на loopback (`127.0.0.1` / `::1`); лимит одновременных задач — действует.
- Контейнер снифается; mux в `.bin` нет. mp3 обычно проходит через ffmpeg; мусор/txt падает на ffprobe.
- Пользователю: лимиты как есть, прочие сбои — общая фраза. Детали в логах.
- Время на прогрессе после `done` заморожено (`finished_at`); без него — сумма `runtime_sec` стадий (не «created_at → сейчас»).

### Правки, спикеры, названия

- Сохранение главы пишет `transcript.json`. Первая правка копирует ASR в `transcript.asr.json`.
- Спикер в главе — выпадающий список id диаризации. Человеческие имена — sidecar `speakers.json` (`Имя · SPEAKER_00`); переименование **не** меняет id кластеров. На оглавлении — длительность речи по кластеру.
- Восстановить главу / весь job из ASR. Полный restore ещё **удаляет** `speakers.json`.
- Отчёт не удаляется: если он есть, появляется `report.stale.json`.
- Названия глав правятся на оглавлении (`POST /jobs/{id}/actions/titles`); смена названий тоже помечает отчёт неактуальным.

### Саммари и словарь

- Кнопка **«Протокол встречи»** вызывает Qwen: дайджест текста глав + **один** report-промпт (без extract по каждой главе). Лимит: `ui.summary_max_calls` (demo = **2**), счётчик `summary_usage.json`.
- Шаблон «Вопросы и ответы» выключен.
- Словарь — заглушка: не переписывает транскрипт.

### Плеер

Позиция (время + playing) в `sessionStorage` на job: переход оглавление ↔ глава не сбрасывает место. На странице главы — prev/next.

### Человеческий шлюз D4

- [ ] Короткий клип (`data/test_voice.m4a`) или `voice_002`: upload → прогресс → оглавление → глава
- [ ] Правка реплики / спикера, restore главы, rename спикера, правка названия
- [ ] Кнопка саммари: появляется `report.md`, повтор до лимита 2, дальше отказ бюджета
- [ ] Reload страницы прогресса на готовой задаче: время не «накручивается»
- [ ] Записать `HUMAN_GATE: PASS|FAIL` + одна фраза в `stage_D4.md`

Известные ограничения (не блокер UI): короткие главы — [`ticket_d2_short_chapters.md`](../agent_docs/plans/ticket_d2_short_chapters.md); 5 кластеров vs 4 человека — [`ticket_d1_speaker_clusters.md`](../agent_docs/plans/ticket_d1_speaker_clusters.md); ingest-gate форматов — [`ticket_d4_audio_formats.md`](../agent_docs/plans/ticket_d4_audio_formats.md).

**Не делать на D4:** Playwright, cloud handoff, реальный fetch YouTube/Yandex, пересборка chapters/report `voice_002`.

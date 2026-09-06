# Черновик этапа D4 — веб-интерфейс демки (Фаза A)

**Статус:** PLAN_DRAFT  
**Предшественник:** D3 HUMAN_GATE PASS (merged); diarization threshold 0.85 → ~5 speakers on voice_002 (chapters/report **не** пересобираем в этом этапе).  
**Стратегия:** довести каркас FastAPI до рабочей демки: upload → progress → result → download + лимиты ТЗ §3. Полный пайплайн на клипе в E2E; локальный human gate — браузер на реальном файле (в т.ч. проверка новой 5-spk сборки).  
**Источники:** [`draft_demo_roadmap.md`](draft_demo_roadmap.md) §D4, [`draft_architecture.md`](draft_architecture.md) §5, [`quality_gates.md`](../contracts/quality_gates.md) G4, [`docs/dev_specs.md`](../../docs/dev_specs.md) §demo UI / limits.

---

## 1. Цель

```
browser
  → POST upload (audio)
  → job queued / running (1 concurrent)
  → GET progress (polling; SSE optional)
  → result page (summary, key moments, chapters, draft_warning)
  → download artifacts
  → TTL wipe after result_ttl_hours
```

Не входит: D5 Docker/hardware gate, editing UI, audio player highlight, PDF export, auth кроме IP-лимитов, пересборка D2/D3 артефактов voice_002, prod-only stubs beyond registry errors.

---

## 2. Что уже есть (не строить с нуля)

| Кусок | Состояние |
|---|---|
| `web/app.py` + `/healthz` | каркас D0 |
| `jobs/store.py` | create/get/update job, IP hash (`JOB_IP_SALT`) |
| Pipeline orchestrator + stages through report | D1–D3 на main |
| Config `limits.*`, `ui.*`, `audio.max_*` | demo values in `config/` |
| G4 checklist | contract ready |

Не хватает: routes/templates/static, limits middleware, queue/worker, TTL sweeper, E2E tests, result page binding to report artifacts.

---

## 3. Объём облака (после ✅ → Phase B)

1. Preflight: packed short clip in `cloud_in/inputs/audio/` (85 s `test_voice` or equivalent); `STACK.md`; env names only (`JOB_IP_SALT`, active `*_API_KEY` if full pipeline past ASR needs LLM).
2. Implement web layer per architecture: `/`, `/jobs/{id}`, `/jobs/{id}/result`, `/jobs/{id}/download`, `/jobs/{id}/events`, keep `/healthz`.
3. Wire upload → job store → background worker running existing pipeline; progress via `StageEvent`.
4. Enforce: 1 req/IP/day, 1 concurrent job, size/duration reject before pipeline, TTL delete job dir.
5. Result page: summary, key moments+timecodes, chapters, download; `draft_warning` from config.
6. G4.1–G4.8 + lint; push branch (no force `main`).

**E2E clip strategy:** pytest E2E on packed **short** clip (G4.1). Full voice_002 (~24.5 min) is **local human** path only (or optional long-run outside cloud budget) — cloud must not burn a full meeting unless explicitly approved.

**LLM on E2E:** prefer fixture/resume path if job can start from packed transcript+chapters for result-page tests; upload E2E may stop after ASR or use cassette — decide in Phase B instructions to stay within API caps (`max_calls_per_job`).

---

## 4. G4 (облако)

Как в [`quality_gates.md`](../contracts/quality_gates.md): G4.1–G4.8. Логи без текста транскрипта и без секретов.

---

## 5. Ручной шлюз

Локально в браузере: загрузка реального файла → прогресс → результат → скачивание. Заодно смотрим, что новая диаризация (5 спикеров) выглядит разумно в UI. `HUMAN_GATE` в `stage_D4.md`.

---

## 6. Зависимости

Ожидаемо уже в проекте: FastAPI, Jinja2, httpx/TestClient.  
Новые пакеты — **только с явным approve**. Кандидаты (если не окажется в lock): `jinja2`, `python-multipart` для upload. Не ставить фронтенд-бандлеры.

---

## 7. Данные / pack (после ✅)

| Pack | Зачем |
|---|---|
| `cloud_in/inputs/audio/test_voice.m4a` (или уже лежащий клип) | E2E upload |
| Optional fixture artifacts for result-page unit/E2E without live LLM | faster G4.8 |
| `STACK.md` | versions |

Не класть: `eval/`, `.env`, GGUF, полный `voice_002.m4a` без отдельного approve (тяжёлый для cloud gate).

---

## 8. Критерий готовности Phase A → B

После ✅ пользователя: `coder_D4.md` + `tester_D4.md`, ветка `cursor/demo-d4-web`, pack+handoff.

---

## 9. Открытые вопросы к человеку

1. E2E в облаке: только короткий клип — ок? (рекомендуем да)
2. Полный пайплайн до LLM в cloud E2E или ASR+фикстуры для report page? (рекомендуем: upload E2E до transcript на клипе; result page на packed D3 fixtures — меньше API$)
3. Подтвердить demo лимиты: `max_minutes: 15` при локальном тесте voice_002 (~24.5 мин) — поднять для human gate / profile `dev`, или резать файл?

---

## 10. Не делать

- Пересборку chapters/insights/report для voice_002 в рамках D4.
- Player / editing / PDF.
- Force-push `main`.

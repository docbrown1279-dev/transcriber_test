# Черновик этапа D4 — веб-интерфейс демки (Фаза A)

**Статус:** PLAN_DRAFT (решения по лимитам / локальной разработке зафиксированы)  
**Предшественник:** D3 HUMAN_GATE PASS; diarization 0.85 → ~5 speakers (chapters/report **не** пересобираем).  
**Стратегия:** довести FastAPI-каркас до рабочей демки **локально** (без Cursor Cloud handoff): upload → progress → result → download + лимиты. Облако оставляем для исследовательских A/B; конечный UI/пайплайн ведём здесь, чтобы видеть процесс и не жечь токены.  
**Источники:** [`draft_demo_roadmap.md`](draft_demo_roadmap.md) §D4, [`draft_architecture.md`](draft_architecture.md) §5, [`quality_gates.md`](../contracts/quality_gates.md) G4, [`docs/dev_specs.md`](../../docs/dev_specs.md) §demo UI / limits.

---

## 1. Цель

```
browser
  → POST upload (audio)
  → if duration > audio.max_minutes: warn «клип будет обрезан» (лимит из конфига)
  → job queued / running (1 concurrent)
  → GET progress (polling; SSE optional)
  → result page (summary, key moments, chapters, draft_warning)
  → download artifacts
  → TTL wipe after result_ttl_hours
```

Не входит: D5 Docker/hardware, editing UI, player highlight, PDF, auth кроме IP-лимитов, пересборка D2/D3 voice_002, cloud handoff/pack для D4.

---

## 2. Принятые решения (2026-09-06)

| Тема | Решение |
|---|---|
| Где делаем D4 | **Локально.** Cloud handoff для D4 не планируем. |
| E2E | Короткий клип (~85 с): smoke «в принципе работает» (upload → … → download / result). |
| `audio.max_minutes` | **30** в конфиге (`config/base.yaml` / profile overlay). Крутим позже без смены кода поведения. |
| Длиннее лимита | Не жёсткий отказ: **предупреждение**, что клип **обрежут** до `max_minutes`. Oversize файла (`max_file_size_mb`) — по-прежнему отказ. |
| Chapters/report voice_002 | Не пересобираем в D4; human gate может гонять полный файл в UI. |

UI/вёрстку обсуждаем отдельно (следующий шаг после этого черновика).

---

## 3. Что уже есть

| Кусок | Состояние |
|---|---|
| `web/app.py` + `/healthz` | каркас D0 |
| `jobs/store.py` | create/get/update, IP hash (`JOB_IP_SALT`) |
| Pipeline through report | D1–D3 на main |
| `audio.max_minutes` / `limits.*` / `ui.*` | в конфиге; demo `max_minutes: 30` |
| G4 checklist | контракт; прогон локально |

Не хватает: routes/templates, limits+trim UX, queue/worker, TTL sweeper, E2E на коротком клипе, привязка result page к report-артефактам.

---

## 4. Объём реализации (локально, после ✅ по UI)

1. Web: `/`, `/jobs/{id}`, `/jobs/{id}/result`, `/jobs/{id}/download`, `/jobs/{id}/events`, `/healthz`.
2. Upload → job store → worker на существующем пайплайне; progress через `StageEvent`.
3. Лимиты: 1 req/IP/day, 1 concurrent; `max_file_size_mb` → reject; `max_minutes` → **warn + trim**.
4. Result: summary, key moments, chapters, download, `draft_warning`.
5. G4 локально (`pytest` + ручной браузер). Ветка по желанию `cursor/demo-d4-web` без cloud pack.

E2E: короткий клип из `data/` / fixtures — без полного voice_002 и без обязательного live LLM на каждый прогон (фикстуры/resume для result page допустимы).

---

## 5. G4

Чеклист [`quality_gates.md`](../contracts/quality_gates.md) G4.1–G4.8 — **локальный** прогон. G4.5: oversize reject; over-duration = warn + truncate to `audio.max_minutes`.

---

## 6. Ручной шлюз

Браузер на реальном файле (в т.ч. voice_002 ~24.5 мин &lt; 30). Смотрим UX обрезки на искусственно коротком `max_minutes` при подкрутке. `HUMAN_GATE` → `stage_D4.md`.

---

## 7. Зависимости

FastAPI / Jinja2 / multipart — из существующего стека где возможно. Новые пакеты только с явным approve.

---

## 8. Критерий Phase A → B

После согласования **UI** (отдельное обсуждение): `coder_D4.md` + `tester_D4.md` под локальную работу (без `cloud_in` pack).

---

## 9. Открытые вопросы

Сняты: лимит 30 / trim+warn, E2E short clip, локальная разработка.  
Остаётся: **интерфейс** (страницы, тексты предупреждения обрезки, прогресс) — следующий шаг.

---

## 10. Не делать

- Cloud handoff / burn токенов на D4.
- Пересборку chapters/insights/report voice_002.
- Player / editing / PDF.
- Force-push `main`.

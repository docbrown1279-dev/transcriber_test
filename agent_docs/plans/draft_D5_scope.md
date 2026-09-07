# Черновик этапа D5 — Docker + железо демки (Фаза A)

**Статус:** TEST_PASS — await HUMAN_GATE; gate [`../reports/d5/gate_D5.md`](../reports/d5/gate_D5.md)  
**Предшественник:** D4.1 CLOSED (`toc_mode=b` default; peak RSS ~1.6–2 ГиБ на 10 мин без cgroup).  
**Шлюз:** G5 в [`../contracts/quality_gates.md`](../contracts/quality_gates.md).  
**Стратегия:** **локально** (как D4 / D4.1), без cloud handoff.  
**D5.1 (позже):** GitHub Actions / полный CI workflow — **не** в D5.

---

## 1. Цель

1. Упаковать демку в **воспроизводимый Docker-образ** (задел под CI/CD, без workflow-файла).
2. **Собрать образ и прогнать тесты внутри контейнера** (unit + soft regression на `data/test_voice.m4a`).
3. Прогнать пайплайн (default `toc_mode=b`) под **`--cpus=2 --memory=8g`** на **15‑минутном** срезе.
4. Wall time + peak RSS по этапам; при промахе по времени — рекомендация снизить `audio.max_minutes` до 10–15 (ТЗ §3, §10).
5. Вердикт человека: публиковать демку / сначала ужать лимит.

---

## 2. Docker vs Compose

| Вопрос | Решение |
|---|---|
| Dockerfile | **Да** — основа D5 и G5.1. |
| Compose | **Не обязателен** (один сервис). |
| GitHub Actions | **D5.1**, не D5. |
| Тесты в контейнере | **Да** — target `test`/`ci`: `pytest` внутри образа после `docker build`. |

**Итог D5:** `Dockerfile` + `.dockerignore` + команды build/run/test. Compose — нет. Actions — D5.1.

---

## 3. Контекст сборки и `.dockerignore`

### В контекст (не игнорировать)

| Путь | Зачем |
|---|---|
| `pyproject.toml`, `uv.lock` | воспроизводимые зависимости |
| `src/` | приложение |
| `config/` | профили demo |
| `models/` | tracked ONNX (Silero) |
| `tests/` | pytest в контейнере (target `test`) |
| `data/test_voice.m4a` | soft regression / probe (~724 КиБ); **остальной `data/` — ignore** |
| `scripts/bench_*.py` (d4_1 / d5) | замер G5 |
| `.python-version` / `README.md` | по желанию |

Регрессия уже ищет `data/test_voice.m4a` (см. `tests/regression/test_voice_pipeline_regression.py`). В образе путь сохранить: `/app/data/test_voice.m4a` (WORKDIR `/app`).

### В `.dockerignore`

`.git`, `.venv/`, `var/`, **`data/*` кроме `test_voice.m4a`**, `eval/`, `results/`, `agent_docs/`, `docs/`, `cloud_in/`, `cloud_out/`, `.cursor/`, `.trash/`, `prompts/`, `manuals/`, кэши, локальные env/секреты, тяжёлые `models/.cache/**`.

Паттерн (ориентир для Coder):

```dockerignore
data/**
!data/test_voice.m4a
```

### Секреты — только volume / env, не слои образа

- Файлы с ключами **не** `COPY` в образ.
- Рантайм / тест: bind-mount каталога или файла секретов, например  
  `-v /path/to/secrets:/run/secrets:ro`  
  и/или `--env-file` с хоста (файл вне git).
- Приложение читает имена переменных из yaml (`QWEN_API_KEY`, `JOB_IP_SALT`, …); значения приходят из смонтированного env.
- В отчётах и логах контейнера — без значений ключей.

### Модели

- В образ: код + Silero + deps.
- Кэш HF/torch: named volume или bind-mount.
- Cold vs warm start — отдельно в отчёте G5.

---

## 4. Образ (Coder)

- Base: Python **3.12**, `uv` + `--frozen` lockfile.
- System: `ffmpeg`.
- Multi-stage:
  - **builder** — sync extras demo (`asr`, `diarize`, `embed`, `llm`) + optional `dev` для test stage;
  - **runtime** — serve (`transcriber serve` / uvicorn `0.0.0.0:8000`), `HEALTHCHECK` → `/healthz`, non-root, writable `storage_root` volume;
  - **test** — runtime + `tests/` + `data/test_voice.m4a` + dev deps; default CMD: `uv run pytest …` (точный набор — в инструкциях Tester).
- Без GPU; без новых пакетов без ✅.
- GitHub Actions workflow — **не** писать (D5.1).

Пример локального прогона тестов (ориентир):

```bash
docker build --target test -t transcriber:test .
docker run --rm \
  --cpus=2 --memory=8g \
  -v "$PWD/secrets:/run/secrets:ro" \
  -e JOB_IP_SALT=… \
  transcriber:test
```

(точные флаги и какие тесты — Phase B.)

---

## 5. Прогон железа (Tester)

| Параметр | Значение |
|---|---|
| Сборка | `docker build` targets `runtime` + `test` |
| Тесты в контейнере | unit + soft regression (`test_voice`); FAIL/WARN по текущим правилам (`REGRESSION_STRICT`) |
| Лимиты G5 | `--cpus=2 --memory=8g` |
| Аудио G5 | 15‑мин срез `voice_002` → `var/bench/d5/` на хосте, mount в контейнер |
| Режим | `toc_mode=b`; опц. контрольный `a` |
| Peak RSS | G5.4 `< 7 GiB` |
| OOM | FAIL G5.1 |

Отчёт: `agent_docs/reports/d5/` на **хосте** (mount out-dir или `docker cp`).  
Регрессия сегодня пишет в `agent_docs/reports/regression_test_voice.md` — в контейнере либо mount `agent_docs/reports`, либо Coder правит путь отчёта на writable volume (уточнить в Phase B).

---

## 6. Не делать в D5

- **GitHub Actions / GitLab CI** → этап **D5.1**.
- Обязательный Compose / k8s / GPU.
- Cloud handoff / force-push `main`.
- Смена ASR / UI.
- `COPY` секретов в слои; весь `data/` (кроме `test_voice.m4a`).

---

## 7. Зафиксированные решения (rev2)

| # | Тема | Решение |
|---|---|---|
| Q1 | Compose | Не обязателен |
| Q2 | Контекст | + `pyproject`/`uv.lock`; **`data/test_voice.m4a` для регрессии**; остальной `data/` ignore |
| Q3 | Где | Локально |
| Q4 | Клип G5 | 15′ trim; cold/warm в отчёте |
| Q5 | Actions | **D5.1** |
| Q6 | Секреты | **volume** (и/или host `--env-file`), не в образ |
| Q7 | Тесты | **Да:** build `--target test` → `pytest` в контейнере |

---

## 8. После ✅ (Phase B)

- `instructions/coder_D5.md` — Dockerfile (runtime+test), `.dockerignore`, volumes (secrets, cache, storage, reports).
- `instructions/tester_D5.md` — build, in-container pytest, G5 15′/`cpus`/`memory`, отчёт.
- Опц. `contracts/docker_runtime.md` + index; раздел в `manuals/`.
- Roadmap note: вставить **D5.1 — GitHub Actions** после D5.

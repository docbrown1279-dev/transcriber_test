# Ручная проверка (smoke)

Инструкции для человека после облачного этапа. Автошлюзы (gate) — в `agent_docs/reports/`; здесь только то, что стоит прогнать локально глазами/руками.

Перед любым smoke:

```bash
cd /work/speech_rec_test   # корень репо
export PATH="$HOME/.local/bin:$PATH"   # если gh ставили в ~/.local
uv sync
export JOB_IP_SALT=local-dev-salt      # обязателен для healthcheck /healthz
```

Профиль по умолчанию — `demo` (`APP_PROFILE` не задан). Настройка профилей: [`configuration_guide.md`](configuration_guide.md). Облачный цикл: [`cloud_flow.md`](cloud_flow.md).

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
D0 CLOSED (merge) → D1 облако (G1) → ручной шлюз D1 → merge → D2 …
```

Не переходить к D2, пока в `agent_docs/progress/stage_D1.md` нет строки `HUMAN_GATE: PASS`.

---

## Stage D1 — голос → транскрипт

**Смысл этапа:** нормализация, VAD, диаризация, ASR, suggestions (пустой словарь). Облако гоняет **полную** запись `voice_002.m4a` и автопроверки этапа (G1); человек слушает локально после pull.

**Критерий выхода:** `agent_docs/reports/D1/gate_D1.md` = PASS/PASS_WITH_WARNINGS **и** `HUMAN_GATE: PASS` в progress.

### После ingest

Артефакты полного прогона: `agent_docs/reports/D1/` (gate) и копия/путь к `transcript.json` из `cloud_out/artifacts/voice_002/` (после pull).

```bash
uv run python -m transcriber.quality check-transcript path/to/transcript.json
```

### Человеческий шлюз D1

- [ ] Gate G1 в отчёте — PASS или PASS_WITH_WARNINGS  
- [ ] Прослушать 2–3 участка полной записи, включая тихие  
- [ ] Сверить с облачным `transcript.json`  
- [ ] Опционально: WER/CER vs `eval/`  
- [ ] Записать в `agent_docs/progress/stage_D1.md`: `HUMAN_GATE: PASS|FAIL` + одна фраза  

**Не делать на D1:** главы, LLM-отчёт, веб-загрузка (D2–D4).

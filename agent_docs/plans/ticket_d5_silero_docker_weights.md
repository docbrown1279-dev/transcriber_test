# Тикет: Silero ONNX в Docker / gitignore `models/`

**Статус:** OPEN (частичный костыль в Dockerfile)  
**Приоритет:** средний — блокировал `docker compose build` на чистом сервере.

---

## Проблема

- `Dockerfile` делал `COPY models/silero_vad.onnx`, а `/models/` в **`.gitignore`**.
- На сервере после `git clone` файла нет → build падает.
- Runtime умеет скачать веса сам (`get_silero_model_path` в `silero.py`), но **слой образа** этого не делал.

Контракт D5 уже помечал: shipping `models/` в git — backlog D5.1.

---

## Костыль сейчас (сделано)

В `Dockerfile` (targets `runtime` и `test`): `curl` snakers4 Silero v5 с того же URL, что в `silero.py`:

`https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx`

Сборка больше не зависит от локальной `models/` на хосте. Нужен сеть на build-хосте.

---

## Доделать нормально

| id | Что |
|---|---|
| A | Запинить **commit SHA** (не `master`) + проверка **sha256** (`1a153a22…` из D1 parity) |
| B | Решить: трекать `models/silero_vad.onnx` в git (~2.3 МБ) **или** только download-at-build / entrypoint |
| C | Обновить `manuals/docker.md` / `docker_runtime.md` (не требовать локальный models для compose) |
| D | То же для `data/test_voice.m4a` на target `test` (сейчас тоже gitignore+исключение в dockerignore) |

---

## WeSpeaker

Уже ONNX (`speakeronnx`); vs pyannote torch на CPU — ожидаемо на порядок быстрее. Узкое место diarize — число окон embed, не «не тот рантайм». См. `ticket_d5_diarize_speed.md`.

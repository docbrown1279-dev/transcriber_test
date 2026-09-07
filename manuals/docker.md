# Docker (демо, этап D5)

Локальная сборка и прогон демки в контейнере. GitHub Actions — этап **D5.1** (ещё нет).

Контракт: [`agent_docs/contracts/docker_runtime.md`](../agent_docs/contracts/docker_runtime.md).

## Что нужно на хосте

- Docker
- Файлы для контекста (могут быть gitignore): `data/test_voice.m4a`, `models/` (Silero ONNX)
- Файл секретов **вне git** (ключи как в шаблоне `*.example` в корне репо): `JOB_IP_SALT`, ключ LLM демки, опционально `HF_TOKEN`

## Сборка

```bash
docker build --target runtime -t transcriber:runtime .
docker build --target test -t transcriber:test .
```

В контекст попадает только `data/test_voice.m4a` из `data/` (остальное отсекает `.dockerignore`).

## Секреты

Не копировать в образ. Варианты:

```bash
# volume + путь для загрузчика
docker run --rm \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v /path/to/secrets.env:/run/secrets/transcriber.env:ro \
  …

# или инжект в process env с хоста
docker run --rm --env-file /path/to/secrets.env …
```

## Тесты в контейнере

```bash
docker run --rm --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v /path/to/secrets.env:/run/secrets/transcriber.env:ro \
  -v "$PWD/agent_docs/reports:/app/agent_docs/reports" \
  -v "$PWD/agent_docs/reports/d5:/out" \
  transcriber:test
```

Default CMD: `pytest tests/unit tests/contract tests/regression -v`.

Отчёт soft-regression по умолчанию пишет в `/app/agent_docs/reports/regression_test_voice.md`  
(в образе нет git-дерева `agent_docs/` — смонтируйте путь выше **или** попросите @Tester читать `REGRESSION_REPORT_PATH` в `tests/regression/…`).

## Сервер

```bash
docker run --rm -p 8000:8000 \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v /path/to/secrets.env:/run/secrets/transcriber.env:ro \
  -v transcriber-var:/var/transcriber \
  transcriber:runtime
```

Откройте `http://127.0.0.1:8000/`. Health: `/healthz`.

## Железо (G5)

Прогон 15‑мин среза с `--cpus=2 --memory=8g`:

```bash
docker run --rm \
  --cpus=2 --memory=8g \
  -e TRANSCRIBER_DOTENV=/run/secrets/transcriber.env \
  -v /path/to/secrets.env:/run/secrets/transcriber.env:ro \
  -v "$PWD/var/bench/d5:/bench:ro" \
  -v "$PWD/agent_docs/reports/d5:/out" \
  -v transcriber-hf-cache:/home/app/.cache \
  -v transcriber-var:/var/transcriber \
  transcriber:runtime \
  python /app/scripts/bench_d5.py \
    --audio /bench/voice_002_15min.m4a \
    --mode b \
    --out /out/g5_15min.json
```

Альтернатива titles-only A/B на уже готовом job: `python /app/scripts/bench_d4_1.py` (см. D4.1).  
Подробности — [`agent_docs/instructions/tester_D5.md`](../agent_docs/instructions/tester_D5.md).

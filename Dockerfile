# syntax=docker/dockerfile:1
# Multi-stage image for the meeting-transcriber demo (stage D5).
# Targets: builder (deps), runtime (serve), test (pytest).

ARG PYTHON_VERSION=3.12

# ---------------------------------------------------------------------------
# Base: system packages shared by builder / runtime / test
# ---------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim-bookworm AS base

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.22 /uv /uvx /usr/local/bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# ---------------------------------------------------------------------------
# Builder: frozen lock + demo extras (asr, diarize, embed, llm)
# ---------------------------------------------------------------------------
FROM base AS builder

COPY pyproject.toml uv.lock README.md ./
COPY src ./src

RUN uv sync --frozen --no-dev \
        --extra asr \
        --extra diarize \
        --extra embed \
        --extra llm

# ---------------------------------------------------------------------------
# Builder-test: same extras + dependency-groups.dev
# ---------------------------------------------------------------------------
FROM builder AS builder-test

RUN uv sync --frozen \
        --extra asr \
        --extra diarize \
        --extra embed \
        --extra llm \
        --group dev

# ---------------------------------------------------------------------------
# Runtime: non-root serve on 0.0.0.0:8000
# ---------------------------------------------------------------------------
FROM base AS runtime

# Drop git from the final runtime image surface (ffmpeg/curl stay for health + media).
RUN apt-get update \
    && apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && mkdir -p /var/transcriber /home/app/.cache \
    && chown -R app:app /var/transcriber /home/app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app pyproject.toml uv.lock README.md ./
COPY --chown=app:app src ./src
COPY --chown=app:app config ./config
COPY --chown=app:app scripts/bench_d4_1.py scripts/bench_d5.py ./scripts/

# Silero weights are gitignored under /models/; fetch snakers4 ONNX at build time
# (same URL as src/transcriber/vad/silero.py). Ticket: pin commit SHA / checksum.
RUN mkdir -p /app/models \
    && curl -fsSL -o /app/models/silero_vad.onnx \
        "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx" \
    && chown -R app:app /app/models

ENV TRANSCRIBER_STORAGE_ROOT=/var/transcriber \
    HOME=/home/app \
    XDG_CACHE_HOME=/home/app/.cache \
    HF_HOME=/home/app/.cache/huggingface

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=4)"

CMD ["transcriber", "serve", "--host", "0.0.0.0", "--port", "8000"]

# ---------------------------------------------------------------------------
# Test: runtime + tests + test_voice + pytest
# ---------------------------------------------------------------------------
FROM base AS test

RUN useradd --create-home --uid 1000 --shell /usr/sbin/nologin app \
    && mkdir -p /var/transcriber /home/app/.cache /out \
    && chown -R app:app /var/transcriber /home/app /out

COPY --from=builder-test --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app pyproject.toml uv.lock README.md ./
COPY --chown=app:app src ./src
COPY --chown=app:app config ./config
COPY --chown=app:app scripts/bench_d4_1.py scripts/bench_d5.py ./scripts/
COPY --chown=app:app tests ./tests
COPY --chown=app:app data/test_voice.m4a ./data/test_voice.m4a

RUN mkdir -p /app/models \
    && curl -fsSL -o /app/models/silero_vad.onnx \
        "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx" \
    && chown -R app:app /app/models

# Writable stub so soft-regression can write its default report path inside the
# image when agent_docs/ is not mounted (prefer mounting or REGRESSION_REPORT_PATH).
RUN mkdir -p /app/agent_docs/reports \
    && chown -R app:app /app/agent_docs

ENV TRANSCRIBER_STORAGE_ROOT=/var/transcriber \
    HOME=/home/app \
    XDG_CACHE_HOME=/home/app/.cache \
    HF_HOME=/home/app/.cache/huggingface

USER app

# Unit + contract + soft regression (marked slow+regression). Override as needed.
CMD ["pytest", "tests/unit", "tests/contract", "tests/regression", "-v"]

"""Веб-приложение FastAPI: healthz, Jinja UI, фоновый воркер задач."""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request

from transcriber.config.loader import load_config, load_dotenv_into_environ
from transcriber.jobs.queue import JobQueue
from transcriber.jobs.ttl import sweep_expired_jobs
from transcriber.web.health import run_self_check
from transcriber.web.public_errors import USER_SERVER
from transcriber.web.routes import render_error, router

_WEB_DIR = Path(__file__).resolve().parent

logger = logging.getLogger("transcriber.web")


def configure_logging(level: str = "INFO") -> None:
    """Включает логи пакета transcriber в stderr (uvicorn access их не показывает)."""
    numeric = getattr(logging, level.upper(), logging.INFO)
    package = logging.getLogger("transcriber")
    package.setLevel(numeric)
    if not any(isinstance(handler, logging.StreamHandler) for handler in package.handlers):
        handler = logging.StreamHandler()
        handler.setLevel(numeric)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                datefmt="%H:%M:%S",
            )
        )
        package.addHandler(handler)
    package.propagate = False


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Стартует TTL-уборку и однопоточный воркер; останавливает их на shutdown."""
    load_dotenv_into_environ()
    cfg = load_config()
    configure_logging(cfg.app.log_level)
    key_env = cfg.llm.active_backend.api_key_env
    if os.environ.get(key_env):
        logger.info("LLM key env %s is set (value not logged)", key_env)
    else:
        logger.warning(
            "LLM key env %s is missing; titles/insights will fail until .env is loaded",
            key_env,
        )
    storage = Path(cfg.app.storage_root)
    storage.mkdir(parents=True, exist_ok=True)
    sweep_expired_jobs(storage)
    queue = JobQueue(storage, cfg)
    queue.start()
    app.state.cfg = cfg
    app.state.storage_root = storage
    app.state.job_queue = queue
    logger.info("web demo started profile=%s", cfg.app.profile)
    try:
        yield
    finally:
        queue.stop()


def create_app() -> FastAPI:
    """Собирает FastAPI-приложение демки."""
    configure_logging(os.environ.get("APP_LOG_LEVEL", "INFO"))
    load_dotenv_into_environ()
    application = FastAPI(
        title="Meeting Transcriber Demo",
        description="Веб-сервис протоколирования встреч (D4)",
        version="0.4.0",
        lifespan=lifespan,
    )
    application.mount(
        "/static",
        StaticFiles(directory=_WEB_DIR / "static"),
        name="static",
    )
    application.include_router(router)

    @application.exception_handler(Exception)
    async def unhandled_error(request: Request, exc: Exception) -> Any:
        """Не отдаёт traceback во фронт; подробности только в логе."""
        if isinstance(exc, (StarletteHTTPException, RequestValidationError)):
            raise exc
        logger.exception("unhandled web error")
        return render_error(request, 500, USER_SERVER, expose=True)

    @application.get("/healthz")
    async def healthz() -> Any:
        """Эндпоинт проверки работоспособности сервиса и доступности зависимостей."""
        is_healthy, components = run_self_check()
        payload = {
            "status": "healthy" if is_healthy else "unhealthy",
            "components": {
                k: {
                    "status": v.status,
                    "message": v.message,
                    "details": v.details,
                }
                for k, v in components.items()
            },
        }
        if not is_healthy:
            failing = [k for k, v in components.items() if v.status != "ok"]
            payload["failing_components"] = failing  # type: ignore[assignment]
            return JSONResponse(status_code=503, content=payload)
        return JSONResponse(status_code=200, content=payload)

    return application


app = create_app()

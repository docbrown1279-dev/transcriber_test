"""Веб-приложение FastAPI: healthz + HTML stubs for D4 UI preview."""

from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from transcriber.web.health import run_self_check

_WEB_DIR = Path(__file__).resolve().parent
_STUBS_DIR = _WEB_DIR / "static" / "stubs"

app = FastAPI(
    title="Meeting Transcriber Demo",
    description="Веб-сервис протоколирования встреч (D4 stubs + healthz)",
    version="0.1.0",
)

app.mount("/static", StaticFiles(directory=_WEB_DIR / "static"), name="static")


@app.get("/healthz")
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


@app.get("/")
async def stub_home() -> FileResponse:
    """Временный вход на stub загрузки (пока нет боевого UI)."""
    return FileResponse(_STUBS_DIR / "upload.html")


@app.get("/stubs/upload")
async def stub_upload() -> FileResponse:
    return FileResponse(_STUBS_DIR / "upload.html")


@app.get("/stubs/result")
async def stub_result() -> FileResponse:
    return FileResponse(_STUBS_DIR / "result.html")


@app.get("/stubs/chapter")
async def stub_chapter() -> FileResponse:
    return FileResponse(_STUBS_DIR / "chapter.html")

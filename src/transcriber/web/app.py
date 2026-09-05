"""Веб-приложение FastAPI со стартовой самодиагностикой /healthz."""

from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from transcriber.web.health import run_self_check

app = FastAPI(
    title="Meeting Transcriber Demo",
    description="Веб-сервис протоколирования встреч (этап D0: каркас и порты)",
    version="0.1.0",
)


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

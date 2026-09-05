"""События этапов конвейера обработки."""

from pydantic import BaseModel, ConfigDict, Field


class StageEvent(BaseModel):
    """Событие прогресса или изменения статуса этапа конвейера."""

    model_config = ConfigDict(extra="forbid")

    stage: str
    status: str
    pct: int = Field(ge=0, le=100)
    message: str | None = None
    runtime_sec: float | None = None

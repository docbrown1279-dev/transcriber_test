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
    # Optional ETA for the *current* step (seconds); UI shows Russian label.
    eta_sec: float | None = Field(default=None, ge=0.0)
    # Optional whole-file remaining ETA (seconds); paired with eta_sec for dual label.
    eta_total_sec: float | None = Field(default=None, ge=0.0)

"""Pydantic models for pipeline JSON artifacts.

Restored locally: the cloud D0/D1 commits imported this package but never added it to git.
Schemas follow agent_docs/contracts/pipeline_artifacts.md and tests/fixtures/artifacts/*.min.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

T = TypeVar("T", bound=BaseModel)


def _round3(value: float) -> float:
    return round(float(value), 3)


class TimeInterval(BaseModel):
    """Временной интервал с проверкой end > start и неотрицательных границ."""

    model_config = ConfigDict(extra="forbid")

    start: float
    end: float

    @field_validator("start", "end")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("time must be non-negative")
        return _round3(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> TimeInterval:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class AudioSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    size_bytes: int = Field(ge=0)
    duration_sec: float = Field(ge=0)


class AudioNormalized(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    sample_rate: int = Field(gt=0)
    channels: int = Field(gt=0)


class AudioLoudness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rms_dbfs: float
    peak_dbfs: float
    gain_db: float
    gain_applied: bool


class AudioArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    source: AudioSource
    normalized: AudioNormalized
    loudness: AudioLoudness
    runtime_sec: float = Field(ge=0)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


class SpeechArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    detector: str
    fallback_used: bool = False
    regions: list[TimeInterval]
    fallback_regions: list[TimeInterval] = Field(default_factory=list)
    speech_sec: float = Field(ge=0)
    runtime_sec: float = Field(ge=0)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


class TurnItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    start: float
    end: float
    speaker: str

    @field_validator("start", "end")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("time must be non-negative")
        return _round3(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> TurnItem:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class TurnMergeInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")

    same_speaker_gap_sec: float = Field(ge=0)
    absorb_shorter_than_sec: float = Field(ge=0)


class TurnsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    diarizer: str
    speaker_count: int = Field(ge=0)
    turns: list[TurnItem]
    holes: list[TimeInterval] = Field(default_factory=list)
    merge: TurnMergeInfo
    runtime_sec: float = Field(ge=0)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


class TranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    turn_id: str
    start: float
    end: float
    speaker: str
    text: str
    gain_db: float = 0.0
    empty: bool = False

    @field_validator("start", "end")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("time must be non-negative")
        return _round3(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> TranscriptSegment:
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        return self


class TranscriptArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    engine: str
    language: str = "ru"
    segments: list[TranscriptSegment]
    holes: list[TimeInterval] = Field(default_factory=list)
    max_segment_sec: float = Field(gt=0)
    runtime_sec: float = Field(ge=0)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value

    @model_validator(mode="after")
    def _monotonic_segments(self) -> TranscriptArtifact:
        prev_start = -1.0
        for seg in self.segments:
            if seg.start < prev_start:
                raise ValueError("segments must be monotonic by start time")
            prev_start = seg.start
        return self


class QualityCheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: str
    value: Any = None
    threshold: Any = None
    message: str = ""


class QualityArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    russian_word_ratio: float
    total_words: int = Field(ge=0)
    latin_chars_in_segments: int = Field(ge=0)
    empty_segments: int = Field(ge=0)
    hole_sec_total: float = Field(ge=0)
    oov_words: list[str] = Field(default_factory=list)
    verdict: str
    checks: list[QualityCheckItem] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


class SuggestionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    span: list[int]
    found: str
    suggested: str
    confidence: float
    start: float
    end: float


class SuggestionsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    dictionaries: list[str] = Field(default_factory=list)
    applied: bool = False
    suggestions: list[SuggestionItem] = Field(default_factory=list)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


class ChapterItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    start: float
    end: float
    source_ids: list[str] = Field(min_length=1)
    speakers: list[str] = Field(default_factory=list)
    title: str
    duration_sec: float = Field(ge=0)


class ChapterMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chapters_per_minute: float
    short_chapters: int = Field(ge=0)
    long_chapters: int = Field(ge=0)


class ChaptersArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    chunker: str
    embedding_model: str
    similarity_threshold: float
    chapters: list[ChapterItem]
    metrics: ChapterMetrics
    runtime_sec: float = Field(ge=0)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


class InsightSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    start: float
    end: float
    speaker: str


class KeyPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    src: list[InsightSource] = Field(min_length=1)


class InsightChapter(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    start: float
    end: float
    key_points: list[KeyPoint] = Field(default_factory=list)
    actions: list[Any] = Field(default_factory=list)
    open_questions: list[Any] = Field(default_factory=list)
    asr_notes: list[Any] = Field(default_factory=list)


class InsightsArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    provider: str
    model: str
    prompt_id: str
    chapters: list[InsightChapter]
    llm_calls: int = Field(ge=0)
    runtime_sec: float = Field(ge=0)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


class ReportKeyMoment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    start: float
    end: float
    speaker: str
    chapter_id: str


class ReportSpeakerItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str | None = None
    speech_sec: float = Field(ge=0)


class ReportChapterRef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    title: str
    start: float
    end: float


class ReportArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    summary: str
    key_moments: list[ReportKeyMoment] = Field(default_factory=list)
    speakers: list[ReportSpeakerItem] = Field(default_factory=list)
    chapters: list[ReportChapterRef] = Field(default_factory=list)
    provider: str
    model: str
    llm_calls: int = Field(ge=0)
    draft_warning: bool
    runtime_sec: float = Field(ge=0)

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value

    def validate_for_profile(self, profile: str) -> None:
        """В профиле demo draft_warning обязан быть true."""
        if profile == "demo" and not self.draft_warning:
            raise ValueError("draft_warning must be true in profile demo")


class JobStageItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: str
    status: str
    pct: float = Field(ge=0, le=100)
    runtime_sec: float | None = None
    message: str | None = None


class JobArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str
    job_id: str
    created_at: str
    expires_at: str
    client_ip_hash: str
    state: str
    stages: list[JobStageItem] = Field(default_factory=list)
    error: str | None = None

    @field_validator("schema_version")
    @classmethod
    def _schema_v1(cls, value: str) -> str:
        if value != "1":
            raise ValueError("schema_version must be '1'")
        return value


def load_artifact(path: Path | str, model: type[T]) -> T:
    """Загружает JSON-артефакт и валидирует его моделью."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return model.model_validate(data)


def dump_artifact(artifact: BaseModel, path: Path | str) -> None:
    """Пишет артефакт детерминированно: sorted keys, 3-decimal floats."""
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)

    def _default(obj: Any) -> Any:
        if isinstance(obj, float):
            return _round3(obj)
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

    payload = artifact.model_dump(mode="json")
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=_default)
    out.write_text(text + "\n", encoding="utf-8")

"""Схемы конфигурационных моделей приложения.

Все секции используют extra='forbid' для строгой проверки отсутствия неизвестных ключей.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class AppSectionConfig(BaseModel):
    """Основные параметры приложения и профиля."""

    model_config = ConfigDict(extra="forbid")

    profile: str
    storage_root: str = "./var"
    log_level: str = "INFO"


class AudioGainConfig(BaseModel):
    """Линейное усиление громкости (без компрессии)."""

    model_config = ConfigDict(extra="forbid")

    rms_threshold_dbfs: float = Field(default=-30.0, le=0.0)
    target_dbfs: float = Field(default=-23.0, le=0.0)
    max_db: float = Field(default=18.0, ge=0.0)
    peak_ceiling_dbfs: float = Field(default=-1.0, le=0.0)


class AudioVadPreprocessConfig(BaseModel):
    """VAD-only preprocess (compressor). Never fed to ASR."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    # C3 from eval/d1/4: strong leveling for quiet far-mic speech
    ffmpeg_af: str = "dynaudnorm=f=150:g=7:p=0.9"


class AudioConfig(BaseModel):
    """Параметры нормализации и валидации входного аудио."""

    model_config = ConfigDict(extra="forbid")

    max_minutes: int | None = Field(default=None, gt=0)
    max_file_size_mb: int | None = Field(default=None, gt=0)
    sample_rate: int = Field(default=16000, gt=0)
    channels: int = Field(default=1, gt=0)
    gain: AudioGainConfig = Field(default_factory=AudioGainConfig)
    # Per-turn linear gain inside ASR extracts (research 1e/2)
    asr_per_turn_gain: bool = True
    vad_preprocess: AudioVadPreprocessConfig = Field(
        default_factory=AudioVadPreprocessConfig
    )


class VadConfig(BaseModel):
    """Параметры детекции речевой активности (VAD)."""

    model_config = ConfigDict(extra="forbid")

    engine: str = "silero"
    threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    neg_threshold: float = Field(default=0.35, ge=0.0, le=1.0)
    min_speech_ms: int = Field(default=200, ge=0)
    min_silence_ms: int = Field(default=200, ge=0)
    # disabled | ten_fallback | fsmn_fallback (engines may be stubs until implemented)
    fallback: str = "disabled"
    onnx_threads: int = Field(default=2, ge=1)


class DiarizationMergeConfig(BaseModel):
    """Склейка VAD-фрагментов и реплик после кластеризации."""

    model_config = ConfigDict(extra="forbid")

    same_speaker_gap_sec: float = Field(default=0.3, ge=0.0)
    absorb_turn_shorter_than_sec: float = Field(default=1.0, ge=0.0)
    min_hole_sec: float = Field(default=0.5, ge=0.0)
    vad_premerge_gap_sec: float = Field(default=0.3, ge=0.0)


class DiarizationEmbedConfig(BaseModel):
    """Окна эмбеддинга и порог кластеризации спикеров."""

    model_config = ConfigDict(extra="forbid")

    min_sec: float = Field(default=0.4, ge=0.0)
    window_sec: float = Field(default=1.5, gt=0.0)
    step_sec: float = Field(default=0.75, gt=0.0)
    cluster_distance_threshold: float = Field(default=0.5, gt=0.0)


class DiarizationConfig(BaseModel):
    """Параметры диаризации и слияния реплик."""

    model_config = ConfigDict(extra="forbid")

    engine: str
    device: str = "cpu"
    onnx_threads: int = Field(default=2, ge=1)
    merge: DiarizationMergeConfig = Field(default_factory=DiarizationMergeConfig)
    embed: DiarizationEmbedConfig = Field(default_factory=DiarizationEmbedConfig)


class AsrConfig(BaseModel):
    """Параметры автоматического распознавания речи (ASR)."""

    model_config = ConfigDict(extra="forbid")

    engine: str = "gigaam_v3_rnnt"
    device: str = "cpu"
    max_segment_seconds: int = Field(default=25, gt=0)
    subprocess: bool = True


class CorrectionConfig(BaseModel):
    """Параметры подсказок и исправления терминов."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    mode: str = "suggest_only"
    base_ru_dictionary: bool = True
    domain_dictionary: bool = False
    levenshtein_auto_replace: bool = False
    manual_review: bool = False
    min_confidence: float = Field(default=0.6, ge=0.0, le=1.0)


class LateChunkingConfig(BaseModel):
    """Параметры поздней чанкизации."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    provider: str = "disabled"


class ChunkingConfig(BaseModel):
    """Параметры разбиения на главы и семантической сегментации."""

    model_config = ConfigDict(extra="forbid")

    default_mode: str = "speaker_similarity"
    chunker: str = "packing_c"
    embedding_model: str = "rubert_tiny2"
    similarity_threshold: float = Field(default=0.70, ge=0.0, le=1.0)
    packing_max_gap_sec: float = Field(default=2.0, ge=0.0)
    packing_target_words: list[int] = Field(default_factory=lambda: [40, 80])
    merge_max_duration_sec: float = Field(default=180.0, gt=0.0)
    absorb_shorter_than_sec: float = Field(default=5.0, ge=0.0)
    target_chapter_sec: list[int] = Field(default_factory=lambda: [45, 180])
    target_chapters_per_minute: list[float] = Field(default_factory=lambda: [0.4, 0.8])
    warning_chapters_per_minute: list[float] = Field(default_factory=lambda: [0.3, 1.0])
    late_chunking: LateChunkingConfig = Field(default_factory=LateChunkingConfig)


class LlmGenerationConfig(BaseModel):
    """Общие параметры генерации для языковых моделей."""

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    max_tokens: int | None = Field(default=None, ge=1)
    response_format: Literal["json", "text"] | None = None
    timeout_sec: float | None = Field(default=None, gt=0)


class LlmBackendConfig(BaseModel):
    """Настройки транспорта и модели одного API-провайдера."""

    model_config = ConfigDict(extra="forbid")

    client: Literal["gemini", "openai_compat"]
    api_key_env: str
    model: str
    base_url: str | None
    extra_config: str | None = None


class LlmTaskConfig(BaseModel):
    """Пути к промпту и JSON-схеме отдельной LLM-задачи."""

    model_config = ConfigDict(extra="forbid")

    prompt: str
    schema_: str = Field(alias="schema", serialization_alias="schema")
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    response_format: Literal["json", "text"] | None = None


class MeetingInsightsTasksConfig(BaseModel):
    """Настройки извлечения инсайтов и итогового отчёта."""

    model_config = ConfigDict(extra="forbid")

    extract: LlmTaskConfig
    report: LlmTaskConfig


class LlmTasksConfig(BaseModel):
    """Настройки всех LLM-задач приложения."""

    model_config = ConfigDict(extra="forbid")

    chapter_titles: LlmTaskConfig
    meeting_insights: MeetingInsightsTasksConfig


class LlmConfig(BaseModel):
    """Параметры взаимодействия с языковыми моделями."""

    model_config = ConfigDict(extra="forbid")

    mode: Literal["api", "local"]
    backend: str
    max_calls_per_job: int = Field(ge=1)
    base_llm: LlmGenerationConfig
    backends: dict[str, LlmBackendConfig]
    tasks: LlmTasksConfig
    title_max_attempts: int = Field(default=2, ge=1)
    title_max_words: int = Field(default=10, ge=1)
    # sequential = one LLM call per chapter; batch = one call for all (mode A)
    titles_mode: Literal["sequential", "batch"] = "sequential"

    @property
    def active_backend(self) -> LlmBackendConfig:
        """Возвращает конфигурацию выбранного провайдера."""
        try:
            return self.backends[self.backend]
        except KeyError as exc:
            raise ValueError(f"Unknown LLM backend: {self.backend}") from exc

    @property
    def provider(self) -> str:
        """Возвращает ключ транспорта для обратной совместимости."""
        return self.active_backend.client


class LimitsConfig(BaseModel):
    """Ограничения запросов, очередей и времени хранения результатов."""

    model_config = ConfigDict(extra="forbid")

    requests_per_ip_per_day: int | None = Field(default=None, ge=0)
    max_concurrent_jobs: int | None = Field(default=None, ge=1)
    result_ttl_hours: int | None = Field(default=None, ge=0)
    queue_max_size: int | None = Field(default=None, ge=0)


class UiConfig(BaseModel):
    """Параметры пользовательского интерфейса."""

    model_config = ConfigDict(extra="forbid")

    type: str
    show_progress: bool = True
    progress_transport: str = "polling"
    allow_editing: bool = False
    allow_player: bool = False
    draft_warning: bool = True
    summary_max_calls: int = Field(default=2, ge=0)


class PipelineConfig(BaseModel):
    """How TOC titles are produced relative to ASR."""

    model_config = ConfigDict(extra="forbid")

    # a = full ASR then batch titles; b = slice ASR + title when next chapter closes
    toc_mode: Literal["a", "b"] = "b"


class AppConfig(BaseModel):
    """Полная конфигурация приложения для активного профиля."""

    model_config = ConfigDict(extra="forbid")

    app: AppSectionConfig
    audio: AudioConfig
    vad: VadConfig
    diarization: DiarizationConfig
    asr: AsrConfig
    correction: CorrectionConfig
    chunking: ChunkingConfig
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    llm: LlmConfig
    limits: LimitsConfig
    ui: UiConfig

"""Определение стадий конвейера и графа их зависимостей."""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel

from transcriber.audio.normalize import FfmpegAudioNormalizer
from transcriber.config.schema import AppConfig
from transcriber.errors import StageNotImplementedError
from transcriber.llm.titles import apply_titles
from transcriber.models.artifacts import (
    AudioArtifact,
    ChaptersArtifact,
    InsightsArtifact,
    ReportArtifact,
    SpeechArtifact,
    SuggestionsArtifact,
    TranscriptArtifact,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)
from transcriber.registry import build


class JobContext(Protocol):
    """Контекст выполнения задачи конвейера."""

    job_id: str
    job_dir: Path
    source_audio: Path | None


class PipelineStep(Protocol):
    """Протокол отдельного шага конвейера."""

    stage: str
    produces: str
    requires: tuple[str, ...]

    def run(self, ctx: Any, cfg: AppConfig) -> Path:
        """Запускает выполнение шага конвейера."""
        ...


@dataclass(frozen=True)
class StepDefinition:
    """Декларация шага конвейера с целевым артефактом и моделью валидации."""

    stage: str
    produces: str
    requires: tuple[str, ...]
    area: str
    model_cls: type[BaseModel]

    def run(self, ctx: Any, cfg: AppConfig) -> Path:
        """Выполняет шаг конвейера."""
        job_dir = Path(getattr(ctx, "job_dir", ctx))
        job_id = getattr(ctx, "job_id", job_dir.name)

        if self.stage == "normalize":
            source_audio = getattr(ctx, "source_audio", None)
            if source_audio is None:
                # Поиск исходного аудиофайла в job_dir
                candidates = [
                    f
                    for f in job_dir.iterdir()
                    if f.is_file()
                    and f.name not in {"normalized.wav", "vad_input.wav"}
                    and not f.name.endswith(".json")
                    and not f.name.startswith(".")
                    and not f.name.startswith("_")
                ]
                if not candidates:
                    raise FileNotFoundError(f"No source audio file found in {job_dir}")
                source_path = candidates[0]
            else:
                source_path = Path(source_audio)

            normalizer = FfmpegAudioNormalizer()
            normalizer.normalize(source=source_path, dest=job_dir, cfg=cfg.audio, job_id=job_id)
            return job_dir / self.produces

        if self.stage == "vad":
            audio_art = load_artifact(job_dir / "audio.json", AudioArtifact)
            vad_name = audio_art.vad_input.path if audio_art.vad_input.path else "vad_input.wav"
            wav_path = job_dir / vad_name
            if not wav_path.is_file():
                wav_path = job_dir / "normalized.wav"
            detector = build("vad", cfg.vad.engine, cfg.app.profile)
            detector.detect(wav_path, cfg.vad, job_id=job_id)
            return job_dir / self.produces

        if self.stage == "diarize":
            wav_path = job_dir / "normalized.wav"
            speech_artifact = load_artifact(job_dir / "speech.json", SpeechArtifact)
            diarizer = build("diarization", cfg.diarization.engine, cfg.app.profile)
            diarizer.diarize(wav_path, speech_artifact, cfg.diarization, job_id=job_id)
            return job_dir / self.produces

        if self.stage == "asr":
            wav_path = job_dir / "normalized.wav"
            turns_artifact = load_artifact(job_dir / "turns.json", TurnsArtifact)
            engine = build("asr", cfg.asr.engine, cfg.app.profile)
            engine.transcribe(wav_path, turns_artifact, cfg.asr, job_id=job_id)
            return job_dir / self.produces

        if self.stage == "correction_suggest":
            transcript = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
            suggester = build("correction", "dictionary_suggest", cfg.app.profile)
            suggestions = suggester.suggest(transcript, cfg.correction, job_id=job_id)
            out_file = job_dir / self.produces
            dump_artifact(suggestions, out_file)
            return out_file

        if self.stage == "chunk":
            transcript = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
            embedder = build("embeddings", cfg.chunking.embedding_model, cfg.app.profile)
            chunker = build("chunking", cfg.chunking.chunker, cfg.app.profile)
            chapters = chunker.chunk(transcript, embedder, cfg.chunking)
            out_file = job_dir / self.produces
            dump_artifact(chapters, out_file)
            return out_file

        if self.stage == "titles":
            transcript = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
            chapters = load_artifact(job_dir / "chapters.json", ChaptersArtifact)
            client = build("llm", cfg.llm.provider, cfg.app.profile)
            titled_chapters, _calls = apply_titles(chapters, transcript, client, cfg.llm)
            out_file = job_dir / self.produces
            dump_artifact(titled_chapters, out_file)
            return out_file

        raise StageNotImplementedError(stage=self.stage)


# Девять стадий в строгом соответствии с контрактом
PIPELINE_STEPS: list[StepDefinition] = [
    StepDefinition(
        stage="normalize",
        produces="audio.json",
        requires=(),
        area="audio",
        model_cls=AudioArtifact,
    ),
    StepDefinition(
        stage="vad",
        produces="speech.json",
        requires=("audio.json",),
        area="vad",
        model_cls=SpeechArtifact,
    ),
    StepDefinition(
        stage="diarize",
        produces="turns.json",
        requires=("audio.json", "speech.json"),
        area="diarization",
        model_cls=TurnsArtifact,
    ),
    StepDefinition(
        stage="asr",
        produces="transcript.json",
        requires=("audio.json", "turns.json"),
        area="asr",
        model_cls=TranscriptArtifact,
    ),
    StepDefinition(
        stage="correction_suggest",
        produces="suggestions.json",
        requires=("transcript.json",),
        area="correction",
        model_cls=SuggestionsArtifact,
    ),
    StepDefinition(
        stage="chunk",
        produces="chapters.json",
        requires=("transcript.json",),
        area="chunking",
        model_cls=ChaptersArtifact,
    ),
    StepDefinition(
        stage="titles",
        produces="chapters.json",
        requires=("chapters.json", "transcript.json"),
        area="llm",
        model_cls=ChaptersArtifact,
    ),
    StepDefinition(
        stage="insights_extract",
        produces="insights.json",
        requires=("chapters.json",),
        area="llm",
        model_cls=InsightsArtifact,
    ),
    StepDefinition(
        stage="report",
        produces="report.json",
        requires=("insights.json", "chapters.json"),
        area="export",
        model_cls=ReportArtifact,
    ),
]

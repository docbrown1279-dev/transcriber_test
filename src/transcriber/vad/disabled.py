"""Отключенный VAD (dev-режим): возвращает один интервал на всю длительность файла."""

import time
from pathlib import Path

import soundfile as sf

from transcriber.config.schema import VadConfig
from transcriber.models.artifacts import SpeechArtifact, TimeInterval, dump_artifact
from transcriber.vad.base import VoiceActivityDetector


class DisabledVadDetector(VoiceActivityDetector):
    """VAD-заглушка: считает весь аудиофайл речевым интервалом."""

    name: str = "disabled"

    def detect(
        self,
        wav: Path,
        cfg: VadConfig,
        job_id: str | None = None,
    ) -> SpeechArtifact:
        """Создает единственный речевой регион [0.0, total_duration]."""
        t0 = time.time()
        wav_path = Path(wav)
        if not wav_path.is_file():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        info = sf.info(str(wav_path))
        duration = round(float(info.duration), 3)

        resolved_job_id = job_id or wav_path.parent.name
        regions = [TimeInterval(start=0.0, end=duration)] if duration > 0 else []

        artifact = SpeechArtifact(
            schema_version="1",
            job_id=resolved_job_id,
            detector="disabled",
            fallback_used=False,
            regions=regions,
            fallback_regions=[],
            speech_sec=duration,
            runtime_sec=round(time.time() - t0, 3),
        )

        artifact_path = wav_path.parent / "speech.json"
        dump_artifact(artifact, artifact_path)
        return artifact

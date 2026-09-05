"""Нормализация аудио: передискретизация в 16 кГц моно WAV и расчет/применение усиления."""

import subprocess
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from transcriber.audio.base import AudioNormalizer
from transcriber.audio.gain import calculate_gain
from transcriber.config.schema import AudioConfig
from transcriber.models.artifacts import (
    AudioArtifact,
    AudioLoudness,
    AudioNormalized,
    AudioSource,
    dump_artifact,
)
from transcriber.web.health import probe_audio_file


class FfmpegAudioNormalizer(AudioNormalizer):
    """Компонент нормализации аудио с помощью ffmpeg и оценки громкости."""

    def normalize(
        self,
        source: Path,
        dest: Path,
        cfg: AudioConfig,
        job_id: str | None = None,
    ) -> AudioArtifact:
        """Нормализует исходный аудиофайл в 16 кГц моно WAV и применяет линейное усиление."""
        t0 = time.time()
        source_path = Path(source)
        if not source_path.is_file():
            raise FileNotFoundError(f"Source audio file not found: {source_path}")

        if dest.is_dir() or not dest.suffix:
            job_dir = dest
            dest_wav = job_dir / "normalized.wav"
        else:
            job_dir = dest.parent
            dest_wav = dest

        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        resolved_job_id = job_id or job_dir.name

        # Получаем метаданные исходного файла
        probe = probe_audio_file(source_path)
        source_duration = float(probe["duration_sec"])
        source_size = int(probe["size_bytes"])

        # Шаг 1: Конвертация во временный 16 кГц моно WAV
        tmp_wav = job_dir / "_temp_raw_16k.wav"
        cmd_convert = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source_path),
            "-ar",
            str(cfg.sample_rate),
            "-ac",
            str(cfg.channels),
            str(tmp_wav),
        ]
        subprocess.run(cmd_convert, check=True)

        try:
            # Шаг 2: Измерение RMS и пикового уровня
            data, sr = sf.read(str(tmp_wav))
            if len(data) == 0:
                peak_dbfs = -100.0
                rms_dbfs = -100.0
            else:
                peak = float(np.max(np.abs(data)))
                peak_dbfs = float(20.0 * np.log10(peak)) if peak > 0 else -100.0
                rms = float(np.sqrt(np.mean(data**2)))
                rms_dbfs = float(20.0 * np.log10(rms)) if rms > 0 else -100.0

            # Шаг 3: Расчет линейного усиления
            gain_res = calculate_gain(
                rms_dbfs=rms_dbfs,
                peak_dbfs=peak_dbfs,
                threshold_dbfs=cfg.gain_rms_threshold_dbfs,
                target_dbfs=cfg.gain_target_dbfs,
                max_gain_db=cfg.gain_max_db,
                peak_ceiling_dbfs=cfg.gain_peak_ceiling_dbfs,
            )

            # Шаг 4: Применение линейного усиления если требуется
            if gain_res.gain_applied and gain_res.gain_db > 0:
                cmd_gain = [
                    "ffmpeg",
                    "-y",
                    "-v",
                    "error",
                    "-i",
                    str(tmp_wav),
                    "-af",
                    f"volume={gain_res.gain_db:.3f}dB",
                    str(dest_wav),
                ]
                subprocess.run(cmd_gain, check=True)
            else:
                tmp_wav.replace(dest_wav)
        finally:
            if tmp_wav.exists():
                tmp_wav.unlink(missing_ok=True)

        runtime_sec = round(time.time() - t0, 3)

        artifact = AudioArtifact(
            schema_version="1",
            job_id=resolved_job_id,
            source=AudioSource(
                filename=source_path.name,
                size_bytes=source_size,
                duration_sec=round(source_duration, 3),
            ),
            normalized=AudioNormalized(
                path="normalized.wav",
                sample_rate=cfg.sample_rate,
                channels=cfg.channels,
            ),
            loudness=AudioLoudness(
                rms_dbfs=round(rms_dbfs, 3),
                peak_dbfs=round(peak_dbfs, 3),
                gain_db=round(gain_res.gain_db, 3),
                gain_applied=gain_res.gain_applied,
            ),
            runtime_sec=runtime_sec,
        )

        artifact_path = job_dir / "audio.json"
        dump_artifact(artifact, artifact_path)
        return artifact

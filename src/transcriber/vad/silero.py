"""Детектор голосовой активности (VAD) на базе Silero ONNX."""

import os
import time
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf
from huggingface_hub import hf_hub_download

from transcriber.config.schema import VadConfig
from transcriber.models.artifacts import SpeechArtifact, TimeInterval, dump_artifact
from transcriber.vad.base import VoiceActivityDetector

DEFAULT_MODEL_REPO = "deepghs/silero-vad-onnx"
DEFAULT_MODEL_FILE = "silero_vad.onnx"


def get_silero_model_path(models_dir: Path | str = "models") -> Path:
    """Возвращает путь к модели Silero ONNX, скачивая ее при необходимости."""
    dir_path = Path(models_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    model_path = dir_path / DEFAULT_MODEL_FILE

    if not model_path.is_file():
        token = os.environ.get("HF_TOKEN")
        downloaded = hf_hub_download(  # nosec B615
            repo_id=DEFAULT_MODEL_REPO,
            filename=DEFAULT_MODEL_FILE,
            local_dir=str(dir_path),
            token=token,
            revision="main",
        )
        return Path(downloaded)

    return model_path


class SileroVadDetector(VoiceActivityDetector):
    """Реализация VoiceActivityDetector на базе Silero VAD ONNX."""

    name: str = "silero"

    def __init__(self, model_path: Path | str | None = None) -> None:
        self._model_path = Path(model_path) if model_path else get_silero_model_path()
        self._session: ort.InferenceSession | None = None

    def _get_session(self) -> ort.InferenceSession:
        if self._session is None:
            self._session = ort.InferenceSession(
                str(self._model_path),
                providers=["CPUExecutionProvider"],
            )
        return self._session

    def detect(
        self,
        wav: Path,
        cfg: VadConfig,
        job_id: str | None = None,
    ) -> SpeechArtifact:
        """Обнаруживает речевые интервалы во входном 16 кГц mono WAV файле."""
        t0 = time.time()
        wav_path = Path(wav)
        if not wav_path.is_file():
            raise FileNotFoundError(f"WAV file not found: {wav_path}")

        session = self._get_session()

        audio_data, sr = sf.read(str(wav_path))
        if sr != 16000:
            raise ValueError(f"Silero VAD expects 16000 Hz audio, got {sr}")
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        audio_float = audio_data.astype(np.float32)
        total_samples = len(audio_float)
        total_duration = total_samples / sr

        chunk_size = 512
        chunk_sec = chunk_size / sr
        state = np.zeros((2, 1, 128), dtype=np.float32)
        sr_tensor = np.array(sr, dtype=np.int64)

        # Вычисление вероятностей речи по чанкам
        probs: list[float] = []
        for i in range(0, total_samples - chunk_size + 1, chunk_size):
            chunk = audio_float[i : i + chunk_size][np.newaxis, :]
            out, state = session.run(None, {"input": chunk, "state": state, "sr": sr_tensor})
            probs.append(float(out[0, 0]))

        # Извлечение интервалов
        threshold = 0.5
        neg_threshold = 0.35
        min_speech_ms = cfg.min_speech_ms
        min_silence_ms = 200

        min_speech_chunks = max(1, int(min_speech_ms / (chunk_sec * 1000)))
        min_silence_chunks = max(1, int(min_silence_ms / (chunk_sec * 1000)))

        triggered = False
        speech_start_idx = 0
        silence_count = 0
        regions: list[TimeInterval] = []

        for idx, prob in enumerate(probs):
            if not triggered:
                if prob >= threshold:
                    triggered = True
                    speech_start_idx = idx
                    silence_count = 0
            else:
                if prob < neg_threshold:
                    silence_count += 1
                    if silence_count >= min_silence_chunks:
                        triggered = False
                        speech_end_idx = idx - silence_count + 1
                        if speech_end_idx - speech_start_idx >= min_speech_chunks:
                            start_sec = round(max(0.0, speech_start_idx * chunk_sec), 3)
                            end_sec = round(min(total_duration, speech_end_idx * chunk_sec), 3)
                            if end_sec > start_sec:
                                regions.append(TimeInterval(start=start_sec, end=end_sec))
                else:
                    silence_count = 0

        if triggered:
            speech_end_idx = len(probs)
            if speech_end_idx - speech_start_idx >= min_speech_chunks:
                start_sec = round(max(0.0, speech_start_idx * chunk_sec), 3)
                end_sec = round(min(total_duration, speech_end_idx * chunk_sec), 3)
                if end_sec > start_sec:
                    regions.append(TimeInterval(start=start_sec, end=end_sec))

        total_speech_sec = round(sum(r.end - r.start for r in regions), 3)
        runtime_sec = round(time.time() - t0, 3)

        resolved_job_id = job_id or wav_path.parent.name

        artifact = SpeechArtifact(
            schema_version="1",
            job_id=resolved_job_id,
            detector="silero",
            fallback_used=False,
            regions=regions,
            fallback_regions=[],
            speech_sec=total_speech_sec,
            runtime_sec=runtime_sec,
        )

        artifact_path = wav_path.parent / "speech.json"
        dump_artifact(artifact, artifact_path)
        return artifact

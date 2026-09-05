"""Детектор голосовой активности (VAD) на базе Silero ONNX.

Aligned with Stage 1f / snakers4 Silero VAD v5:
- ONNX weights from snakers4/silero-vad (not deepghs fork);
- each 512-sample window is prepended with a sliding 64-sample context;
- timestamping matches research ``speech_timestamps`` (pad + temp_end silence).
"""

from __future__ import annotations

import time
import urllib.request
from pathlib import Path

import numpy as np
import onnxruntime as ort
import soundfile as sf

from transcriber.config.schema import VadConfig
from transcriber.models.artifacts import SpeechArtifact, TimeInterval, dump_artifact
from transcriber.vad.base import VoiceActivityDetector

DEFAULT_MODEL_FILE = "silero_vad.onnx"
# Official Silero v5 ONNX used in Stage 1f (sha256 1a153a22…).
SILERO_VAD_URL = (
    "https://raw.githubusercontent.com/snakers4/silero-vad/"
    "master/src/silero_vad/data/silero_vad.onnx"
)
WINDOW_SAMPLES = 512
CONTEXT_SAMPLES = 64
DEFAULT_SPEECH_PAD_MS = 20


def get_silero_model_path(models_dir: Path | str = "models") -> Path:
    """Return path to Silero ONNX, downloading snakers4 weights if missing."""
    dir_path = Path(models_dir)
    dir_path.mkdir(parents=True, exist_ok=True)
    model_path = dir_path / DEFAULT_MODEL_FILE

    if not model_path.is_file():
        urllib.request.urlretrieve(SILERO_VAD_URL, model_path)  # nosec B310  # noqa: S310

    return model_path


def _speech_regions_from_probs(
    probs: list[float],
    *,
    sample_rate: int,
    total_samples: int,
    threshold: float,
    neg_threshold: float,
    min_speech_ms: int,
    min_silence_ms: int,
    speech_pad_ms: int,
) -> list[TimeInterval]:
    """Convert per-window probs to padded speech intervals (Stage 1f algorithm)."""
    window = WINDOW_SAMPLES
    min_speech = int(sample_rate * min_speech_ms / 1000)
    min_silence = int(sample_rate * min_silence_ms / 1000)
    pad = int(sample_rate * speech_pad_ms / 1000)

    triggered = False
    speeches: list[dict[str, int]] = []
    current: dict[str, int] = {}
    temp_end = 0

    for index, prob in enumerate(probs):
        cur = window * index
        if prob >= threshold and not triggered:
            triggered = True
            current = {"start": cur}
            temp_end = 0
            continue
        if triggered and prob < neg_threshold:
            if not temp_end:
                temp_end = cur
            if cur - temp_end >= min_silence:
                current["end"] = temp_end
                if current["end"] - current["start"] >= min_speech:
                    speeches.append(current)
                current = {}
                triggered = False
                temp_end = 0
        elif triggered:
            temp_end = 0

    if triggered:
        current["end"] = total_samples
        if current["end"] - current["start"] >= min_speech:
            speeches.append(current)

    regions: list[TimeInterval] = []
    for row in speeches:
        start_sample = max(0, row["start"] - pad)
        end_sample = min(total_samples, row["end"] + pad)
        if regions:
            prev_end = int(round(regions[-1].end * sample_rate))
            start_sample = max(start_sample, prev_end)
        if end_sample > start_sample:
            regions.append(
                TimeInterval(
                    start=round(start_sample / sample_rate, 6),
                    end=round(end_sample / sample_rate, 6),
                )
            )
    return regions


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

        audio_data, sr = sf.read(str(wav_path), dtype="float32")
        if sr != 16000:
            raise ValueError(f"Silero VAD expects 16000 Hz audio, got {sr}")
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)

        audio_float = np.asarray(audio_data, dtype=np.float32)
        total_samples = len(audio_float)

        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, CONTEXT_SAMPLES), dtype=np.float32)
        sr_tensor = np.array(sr, dtype=np.int64)

        probs: list[float] = []
        for start in range(0, total_samples, WINDOW_SAMPLES):
            chunk = audio_float[start : start + WINDOW_SAMPLES]
            if chunk.shape[0] != WINDOW_SAMPLES:
                padded = np.zeros(WINDOW_SAMPLES, dtype=np.float32)
                padded[: chunk.shape[0]] = chunk
                chunk = padded
            window = np.concatenate(
                [context, chunk.reshape(1, -1)],
                axis=1,
            ).astype(np.float32)
            out, state = session.run(
                None,
                {"input": window, "state": state, "sr": sr_tensor},
            )
            context = window[:, -CONTEXT_SAMPLES:]
            probs.append(float(np.asarray(out).reshape(-1)[0]))

        regions = _speech_regions_from_probs(
            probs,
            sample_rate=sr,
            total_samples=total_samples,
            threshold=cfg.threshold,
            neg_threshold=cfg.neg_threshold,
            min_speech_ms=cfg.min_speech_ms,
            min_silence_ms=cfg.min_silence_ms,
            speech_pad_ms=DEFAULT_SPEECH_PAD_MS,
        )

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

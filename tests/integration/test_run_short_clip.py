"""Интеграционный тест обработки короткого клипа test_voice.m4a."""

from pathlib import Path

import pytest

from transcriber.models.artifacts import TranscriptArtifact, load_artifact
from transcriber.pipeline.orchestrator import run_job
from transcriber.quality.ru_ratio import count_latin_characters


@pytest.mark.requires_inputs
@pytest.mark.slow
def test_d1_int_01_short_clip_produces_valid_transcript(tmp_path: Path) -> None:
    """[D1-INT-01] if models+test_voice.m4a present: run produces valid transcript; latin_chars==0."""
    audio_path = Path("cloud_in/inputs/audio/test_voice.m4a").resolve()
    if not audio_path.is_file():
        pytest.skip(f"Test audio not found: {audio_path}")

    silero_path = Path("models/silero_vad.onnx")
    if not silero_path.is_file():
        pytest.skip("Silero VAD model weights missing in models/silero_vad.onnx")

    job_dir = tmp_path / "job_short_clip"
    artifacts = run_job(
        job_dir=job_dir,
        source_audio=audio_path,
        until="correction_suggest",
    )

    transcript_path = artifacts.get("asr") or (job_dir / "transcript.json")
    assert transcript_path is not None
    assert transcript_path.is_file()

    transcript = load_artifact(transcript_path, TranscriptArtifact)
    assert transcript.language == "ru"
    assert len(transcript.segments) > 0

    # Проверка отсутствия латинских символов в тексте сегментов
    total_latin = sum(count_latin_characters(s.text) for s in transcript.segments)
    assert total_latin == 0

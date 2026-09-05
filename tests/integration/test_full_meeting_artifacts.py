"""Интеграционный тест валидации артефактов полной встречи voice_002."""

from pathlib import Path

import pytest

from transcriber.models.artifacts import (
    AudioArtifact,
    QualityArtifact,
    SpeechArtifact,
    SuggestionsArtifact,
    TranscriptArtifact,
    TurnsArtifact,
    load_artifact,
)
from transcriber.quality.ru_ratio import count_latin_characters


@pytest.mark.requires_inputs
def test_d1_int_02_full_meeting_artifacts_valid() -> None:
    """[D1-INT-02] cloud_out/artifacts/voice_002/transcript.json exists after gate run, validates, latin==0."""
    artifacts_dir = Path("cloud_out/artifacts/voice_002")
    transcript_path = artifacts_dir / "transcript.json"

    if not transcript_path.is_file():
        pytest.skip(
            "Full-meeting artifacts not yet produced in cloud_out/artifacts/voice_002. "
            "Skipping during unit-only CI."
        )

    # 1. Валидация TranscriptArtifact
    transcript = load_artifact(transcript_path, TranscriptArtifact)
    assert transcript.language == "ru"
    assert transcript.engine == "gigaam_v3_rnnt"
    assert len(transcript.segments) > 0

    # 2. Проверка G1.2: Latin characters == 0
    total_latin = sum(count_latin_characters(s.text) for s in transcript.segments)
    assert total_latin == 0

    # 3. Проверка сопутствующего AudioArtifact и монотонности
    assert (artifacts_dir / "audio.json").is_file()
    audio = load_artifact(artifacts_dir / "audio.json", AudioArtifact)
    assert audio.source.duration_sec > 0.0

    for s in transcript.segments:
        assert s.start >= 0.0
        assert s.end > s.start
        assert s.end <= audio.source.duration_sec + 2.0

    # 4. Проверка наличия остальных обязательных артефактов
    assert (artifacts_dir / "speech.json").is_file()
    load_artifact(artifacts_dir / "speech.json", SpeechArtifact)

    assert (artifacts_dir / "turns.json").is_file()
    load_artifact(artifacts_dir / "turns.json", TurnsArtifact)

    assert (artifacts_dir / "suggestions.json").is_file()
    load_artifact(artifacts_dir / "suggestions.json", SuggestionsArtifact)

    if (artifacts_dir / "quality.json").is_file():
        quality = load_artifact(artifacts_dir / "quality.json", QualityArtifact)
        assert quality.latin_chars_in_segments == 0
        assert quality.russian_word_ratio >= 0.90

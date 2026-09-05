"""Контрактные тесты артефактов цепочки речи D1 (audio, speech, turns, transcript, quality, suggestions)."""

from pathlib import Path

from transcriber.models.artifacts import (
    AudioArtifact,
    AudioLoudness,
    AudioNormalized,
    AudioSource,
    QualityArtifact,
    QualityCheckItem,
    SpeechArtifact,
    SuggestionsArtifact,
    TimeInterval,
    TranscriptArtifact,
    TranscriptSegment,
    TurnItem,
    TurnMergeInfo,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)


def test_d1_art_01_speech_chain_artifacts_round_trip(tmp_path: Path) -> None:
    """[D1-ART-01] minimal hand-built audio/speech/turns/transcript/quality/suggestions round-trip models."""
    job_id = "job_contract_test"

    # 1. AudioArtifact
    audio = AudioArtifact(
        schema_version="1",
        job_id=job_id,
        source=AudioSource(
            filename="sample.m4a",
            duration_sec=12.345,
            size_bytes=102400,
        ),
        normalized=AudioNormalized(
            path="normalized.wav",
            sample_rate=16000,
            channels=1,
        ),
        loudness=AudioLoudness(
            rms_dbfs=-24.5,
            peak_dbfs=-2.1,
            gain_db=0.0,
            gain_applied=False,
        ),
        runtime_sec=2.5,
    )
    p_audio = tmp_path / "audio.json"
    dump_artifact(audio, p_audio)
    loaded_audio = load_artifact(p_audio, AudioArtifact)
    assert loaded_audio == audio

    # 2. SpeechArtifact
    speech = SpeechArtifact(
        schema_version="1",
        job_id=job_id,
        detector="silero",
        fallback_used=False,
        regions=[TimeInterval(start=1.0, end=10.5)],
        fallback_regions=[],
        speech_sec=9.5,
        runtime_sec=1.2,
    )
    p_speech = tmp_path / "speech.json"
    dump_artifact(speech, p_speech)
    loaded_speech = load_artifact(p_speech, SpeechArtifact)
    assert loaded_speech == speech

    # 3. TurnsArtifact
    turns = TurnsArtifact(
        schema_version="1",
        job_id=job_id,
        diarizer="wespeaker_onnx",
        speaker_count=2,
        turns=[
            TurnItem(id="t0001", start=1.0, end=5.0, speaker="SPEAKER_00"),
            TurnItem(id="t0002", start=5.5, end=10.5, speaker="SPEAKER_01"),
        ],
        holes=[TimeInterval(start=0.0, end=1.0), TimeInterval(start=5.0, end=5.5)],
        merge=TurnMergeInfo(same_speaker_gap_sec=0.3, absorb_shorter_than_sec=1.0),
        runtime_sec=3.4,
    )
    p_turns = tmp_path / "turns.json"
    dump_artifact(turns, p_turns)
    loaded_turns = load_artifact(p_turns, TurnsArtifact)
    assert loaded_turns == turns

    # 4. TranscriptArtifact
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id=job_id,
        engine="gigaam_v3_rnnt",
        language="ru",
        segments=[
            TranscriptSegment(
                id="s0001",
                turn_id="t0001",
                speaker="SPEAKER_00",
                start=1.0,
                end=5.0,
                text="Здравствуйте коллеги",
                empty=False,
                gain_db=0.0,
            ),
            TranscriptSegment(
                id="s0002",
                turn_id="t0002",
                speaker="SPEAKER_01",
                start=5.5,
                end=10.5,
                text="Добрый день начинаем",
                empty=False,
                gain_db=0.0,
            ),
        ],
        holes=[TimeInterval(start=0.0, end=1.0), TimeInterval(start=5.0, end=5.5)],
        max_segment_sec=25,
        runtime_sec=4.8,
    )
    p_transcript = tmp_path / "transcript.json"
    dump_artifact(transcript, p_transcript)
    loaded_transcript = load_artifact(p_transcript, TranscriptArtifact)
    assert loaded_transcript == transcript

    # 5. QualityArtifact
    quality = QualityArtifact(
        schema_version="1",
        job_id=job_id,
        russian_word_ratio=1.0,
        total_words=4,
        latin_chars_in_segments=0,
        empty_segments=0,
        hole_sec_total=1.5,
        oov_words=[],
        verdict="pass",
        checks=[
            QualityCheckItem(
                id="G1.1",
                status="pass",
                threshold=0.90,
                value=1.0,
                message="Russian word ratio 1.0",
            ),
            QualityCheckItem(
                id="G1.2",
                status="pass",
                threshold=0,
                value=0,
                message="Latin characters count 0",
            ),
        ],
    )
    p_quality = tmp_path / "quality.json"
    dump_artifact(quality, p_quality)
    loaded_quality = load_artifact(p_quality, QualityArtifact)
    assert loaded_quality == quality

    # 6. SuggestionsArtifact
    suggestions = SuggestionsArtifact(
        schema_version="1",
        job_id=job_id,
        dictionaries=[],
        applied=False,
        suggestions=[],
    )
    p_suggestions = tmp_path / "suggestions.json"
    dump_artifact(suggestions, p_suggestions)
    loaded_suggestions = load_artifact(p_suggestions, SuggestionsArtifact)
    assert loaded_suggestions == suggestions

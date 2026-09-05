"""Тесты проверок качества шлюза G1 (Russian ratio, Latin contamination, empty segments)."""

from transcriber.models.artifacts import TranscriptArtifact, TranscriptSegment
from transcriber.quality.checks import build_quality_artifact
from transcriber.quality.ru_ratio import russian_word_ratio


def test_d1_q_01_pure_cyrillic_passes_g1_1_and_g1_2() -> None:
    """[D1-Q-01] pure Cyrillic sample -> ratio 1.0, latin 0 -> pass G1.1/G1.2."""
    segments = [
        TranscriptSegment(
            id="s0001",
            turn_id="t0001",
            speaker="SPEAKER_00",
            start=0.0,
            end=3.0,
            text="Здравствуйте коллеги начинаем наше рабочее совещание",
            empty=False,
            gain_db=0.0,
        ),
        TranscriptSegment(
            id="s0002",
            turn_id="t0001",
            speaker="SPEAKER_00",
            start=3.0,
            end=6.0,
            text="Сегодня мы обсудим ключевые архитектурные решения",
            empty=False,
            gain_db=0.0,
        ),
    ]
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job_q1",
        engine="gigaam_v3_rnnt",
        language="ru",
        max_segment_sec=25,
        runtime_sec=1.0,
        segments=segments,
        holes=[],
    )

    quality = build_quality_artifact(transcript, audio_duration_sec=6.0)

    assert quality.russian_word_ratio == 1.0
    assert quality.latin_chars_in_segments == 0
    assert quality.empty_segments == 0
    assert quality.verdict == "pass"

    g1_1 = next(c for c in quality.checks if c.id == "G1.1")
    assert g1_1.status == "pass"

    g1_2 = next(c for c in quality.checks if c.id == "G1.2")
    assert g1_2.status == "pass"


def test_d1_q_02_planted_latin_token_fails_g1_2_and_low_ratio_fails_g1_1() -> None:
    """[D1-Q-02] planted Latin token -> G1.2 fail; ratio below 0.90 -> G1.1 fail."""
    # 2 русских слова, 8 латинских слов -> ratio 0.20 (< 0.90), latin_chars > 0
    segments = [
        TranscriptSegment(
            id="s0001",
            turn_id="t0001",
            speaker="SPEAKER_00",
            start=0.0,
            end=5.0,
            text="Привет hello world system architecture test framework pipeline",
            empty=False,
            gain_db=0.0,
        ),
    ]
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job_q2",
        engine="gigaam_v3_rnnt",
        language="ru",
        max_segment_sec=25,
        runtime_sec=1.0,
        segments=segments,
        holes=[],
    )

    quality = build_quality_artifact(transcript, audio_duration_sec=5.0)

    assert quality.russian_word_ratio < 0.90
    assert quality.latin_chars_in_segments > 0
    assert quality.verdict == "fail"

    g1_1 = next(c for c in quality.checks if c.id == "G1.1")
    assert g1_1.status == "fail"

    g1_2 = next(c for c in quality.checks if c.id == "G1.2")
    assert g1_2.status == "fail"


def test_d1_q_03_empty_segments_excluded_no_zero_division() -> None:
    """[D1-Q-03] empty segments excluded from ratio; no ZeroDivision."""
    # Полностью пустые сегменты или содержащие только пробелы и пунктуацию
    empty_segments = [
        TranscriptSegment(
            id="s0001",
            turn_id="t0001",
            speaker="SPEAKER_00",
            start=0.0,
            end=2.0,
            text="",
            empty=True,
            gain_db=0.0,
        ),
        TranscriptSegment(
            id="s0002",
            turn_id="t0001",
            speaker="SPEAKER_00",
            start=2.0,
            end=4.0,
            text="   ... ---  ",
            empty=True,
            gain_db=0.0,
        ),
    ]
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job_q3",
        engine="gigaam_v3_rnnt",
        language="ru",
        max_segment_sec=25,
        runtime_sec=1.0,
        segments=empty_segments,
        holes=[],
    )

    # Не должно бросать ZeroDivisionError
    res = russian_word_ratio(empty_segments)
    assert res.ratio == 1.0
    assert res.total_words == 0
    assert res.russian_words == 0
    assert res.latin_chars == 0

    quality = build_quality_artifact(transcript, audio_duration_sec=4.0)
    assert quality.russian_word_ratio == 1.0
    assert quality.empty_segments == 2

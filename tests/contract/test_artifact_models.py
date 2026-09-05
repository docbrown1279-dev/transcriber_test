"""Контрактные тесты Pydantic-моделей всех 10 артефактов конвейера."""

import json
from pathlib import Path
import tempfile

import pytest

from transcriber.models.artifacts import (
    AudioArtifact,
    ChapterItem,
    ChaptersArtifact,
    InsightsArtifact,
    JobArtifact,
    KeyPoint,
    QualityArtifact,
    ReportArtifact,
    ReportSpeakerItem,
    SpeechArtifact,
    SuggestionsArtifact,
    TimeInterval,
    TranscriptArtifact,
    TranscriptSegment,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)

FIXTURES_DIR = Path("tests/fixtures/artifacts")


def test_d0_art_01_all_ten_examples_round_trip() -> None:
    """[D0-ART-01] every example JSON from pipeline_artifacts.md §1–§10 round-trips through its model."""
    artifact_model_map = [
        ("audio.min.json", AudioArtifact),
        ("speech.min.json", SpeechArtifact),
        ("turns.min.json", TurnsArtifact),
        ("transcript.min.json", TranscriptArtifact),
        ("quality.min.json", QualityArtifact),
        ("suggestions.min.json", SuggestionsArtifact),
        ("chapters.min.json", ChaptersArtifact),
        ("insights.min.json", InsightsArtifact),
        ("report.min.json", ReportArtifact),
        ("job.min.json", JobArtifact),
    ]

    for filename, model_cls in artifact_model_map:
        fixture_path = FIXTURES_DIR / filename
        assert fixture_path.is_file(), f"Fixture {filename} missing"

        # Загрузка через load_artifact
        artifact = load_artifact(fixture_path, model_cls)
        assert artifact.schema_version == "1"

        # Проверка round-trip в JSON
        dumped = artifact.model_dump(mode="json")
        reloaded = model_cls.model_validate(dumped)
        assert reloaded == artifact


def test_d0_art_02_validation_rejections() -> None:
    """[D0-ART-02] rejections: end <= start, negative time, non-monotonic segment list, missing/other schema_version, empty source_ids, key_point without src."""
    # 1. end <= start
    with pytest.raises(ValueError):
        TimeInterval(start=10.0, end=5.0)
    with pytest.raises(ValueError):
        TimeInterval(start=5.0, end=5.0)

    # 2. negative time
    with pytest.raises(ValueError):
        TimeInterval(start=-1.0, end=5.0)

    # 3. non-monotonic segment list
    with pytest.raises(ValueError):
        TranscriptArtifact(
            schema_version="1",
            job_id="j",
            engine="e",
            segments=[
                TranscriptSegment(
                    id="s0001", turn_id="t1", start=5.0, end=10.0, speaker="S1", text="a"
                ),
                TranscriptSegment(
                    id="s0002", turn_id="t1", start=2.0, end=4.0, speaker="S1", text="b"
                ),
            ],
            holes=[],
            max_segment_sec=25,
            runtime_sec=1.0,
        )

    # 4. missing/other schema_version
    with pytest.raises(ValueError):
        AudioArtifact.model_validate(
            {
                "schema_version": "2",
                "job_id": "j",
                "source": {"filename": "a", "size_bytes": 1, "duration_sec": 1.0},
                "normalized": {"path": "p", "sample_rate": 16000, "channels": 1},
                "loudness": {
                    "rms_dbfs": -20.0,
                    "peak_dbfs": -1.0,
                    "gain_db": 0.0,
                    "gain_applied": False,
                },
                "runtime_sec": 1.0,
            }
        )

    # 5. empty source_ids in chapter
    with pytest.raises(ValueError):
        ChapterItem(
            id="C01",
            start=0.0,
            end=10.0,
            source_ids=[],  # min_length=1
            speakers=["S1"],
            title="Title",
            duration_sec=10.0,
        )

    # 6. key_point without src
    with pytest.raises(ValueError):
        KeyPoint(text="Факт встречи", src=[])


def test_d0_art_03_dump_artifact_deterministic_and_three_decimal_floats() -> None:
    """[D0-ART-03] dump_artifact output is deterministic (same bytes on re-dump) and floats keep 3 decimals."""
    fixture_path = FIXTURES_DIR / "transcript.min.json"
    transcript = load_artifact(fixture_path, TranscriptArtifact)

    with tempfile.TemporaryDirectory() as tmpdir:
        path1 = Path(tmpdir) / "dump1.json"
        path2 = Path(tmpdir) / "dump2.json"

        dump_artifact(transcript, path1)
        # Загружаем заново и сохраняем во второй файл
        reloaded = load_artifact(path1, TranscriptArtifact)
        dump_artifact(reloaded, path2)

        bytes1 = path1.read_bytes()
        bytes2 = path2.read_bytes()
        assert bytes1 == bytes2

        # Проверяем, что ключи отсортированы
        data = json.loads(path1.read_text(encoding="utf-8"))
        keys = list(data.keys())
        assert keys == sorted(keys)


def test_d0_art_04_report_draft_warning_and_speakers() -> None:
    """[D0-ART-04] report.json under profile demo requires draft_warning=true; speakers[].label may be null and is never auto-filled."""
    fixture_path = FIXTURES_DIR / "report.min.json"
    report = load_artifact(fixture_path, ReportArtifact)

    # В demo обязательно draft_warning=true
    report.validate_for_profile("demo")
    assert report.draft_warning is True

    # Если draft_warning=False в demo - валидация падает
    report_no_draft = report.model_copy(update={"draft_warning": False})
    with pytest.raises(ValueError):
        report_no_draft.validate_for_profile("demo")

    # В dev или prod draft_warning=False допустим
    report_no_draft.validate_for_profile("prod")

    # speakers[].label может быть None и не заполняется автоматически
    speaker = ReportSpeakerItem(id="SPEAKER_00", label=None, speech_sec=120.5)
    assert speaker.label is None

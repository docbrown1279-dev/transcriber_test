"""Тесты планирования стадий конвейера и разрешения статусов."""

from pathlib import Path

import pytest

from transcriber.errors import StageNotImplementedError
from transcriber.models.artifacts import TranscriptArtifact, TranscriptSegment, dump_artifact
from transcriber.pipeline.orchestrator import plan_job, run_stage
from transcriber.pipeline.steps import PIPELINE_STEPS

CONTRACT_ORDER: list[str] = [
    "normalize",
    "vad",
    "diarize",
    "asr",
    "correction_suggest",
    "chunk",
    "titles",
    "insights_extract",
    "report",
]


def test_d0_pln_01_stage_graph_order_equals_contract(tmp_job_dir: Path) -> None:
    """[D0-PLN-01] stage graph order equals the contract order (nine stages)."""
    step_names = [step.stage for step in PIPELINE_STEPS]
    assert step_names == CONTRACT_ORDER

    plans = plan_job(tmp_job_dir)
    assert [p.stage for p in plans] == CONTRACT_ORDER


def test_d0_pln_02_job_seeded_with_transcript_marks_upstream_done(tmp_job_dir: Path) -> None:
    """[D0-PLN-02] a job seeded with a valid transcript.json reports normalize…asr as done and later stages as pending/unavailable."""
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="test_job",
        engine="gigaam_v3_rnnt",
        language="ru",
        segments=[
            TranscriptSegment(
                id="s0001",
                turn_id="t0001",
                start=1.0,
                end=5.0,
                speaker="SPEAKER_00",
                text="Тестовая реплика",
                gain_db=0.0,
                empty=False,
            )
        ],
        holes=[],
        max_segment_sec=25,
        runtime_sec=2.5,
    )
    dump_artifact(transcript, tmp_job_dir / "transcript.json")

    plans = plan_job(tmp_job_dir)
    plan_dict = {p.stage: p.status for p in plans}

    assert plan_dict["normalize"] == "done"
    assert plan_dict["vad"] == "done"
    assert plan_dict["diarize"] == "done"
    assert plan_dict["asr"] == "done"

    for later_stage in ["correction_suggest", "chunk", "titles", "insights_extract", "report"]:
        assert plan_dict[later_stage] in ["pending", "unavailable"]


def test_d0_pln_03_invalid_artifact_not_counted_as_done(tmp_job_dir: Path) -> None:
    """[D0-PLN-03] an invalid produces artifact is not counted as done."""
    # Записываем заведомо невалидный audio.json (отсутствуют обязательные поля)
    invalid_file = tmp_job_dir / "audio.json"
    invalid_file.write_text('{"schema_version": "1", "invalid_content": true}', encoding="utf-8")

    plans = plan_job(tmp_job_dir)
    normalize_plan = next(p for p in plans if p.stage == "normalize")
    assert normalize_plan.status != "done"
    assert normalize_plan.status in ["pending", "unavailable"]


def test_d0_pln_04_calling_unimplemented_stage_raises_and_writes_nothing(tmp_job_dir: Path) -> None:
    """[D0-PLN-04] calling an unimplemented stage raises StageNotImplementedError and writes no artifact file."""
    initial_files = set(tmp_job_dir.iterdir())

    unimplemented_stages = ["insights_extract", "report"]
    for stage in unimplemented_stages:
        with pytest.raises(StageNotImplementedError):
            run_stage(stage, tmp_job_dir)

    current_files = set(tmp_job_dir.iterdir())
    assert current_files == initial_files


def test_d2_pln_01_transcript_then_chapters_update_plan(tmp_job_dir: Path) -> None:
    """[D2-PLN-01] A transcript seeds pending D2 stages, then titled chapters mark both done."""
    from transcriber.models.artifacts import ChapterItem, ChapterMetrics, ChaptersArtifact

    transcript = TranscriptArtifact(
        schema_version="1",
        job_id=tmp_job_dir.name,
        engine="gigaam_v3_rnnt",
        segments=[
            TranscriptSegment(
                id="s0001",
                turn_id="t0001",
                start=1,
                end=61,
                speaker="A",
                text="текст главы",
            )
        ],
        max_segment_sec=60,
        runtime_sec=1,
    )
    dump_artifact(transcript, tmp_job_dir / "transcript.json")
    initial = {item.stage: item.status for item in plan_job(tmp_job_dir)}
    assert initial["chunk"] == "pending"
    assert initial["titles"] == "pending"

    chapters = ChaptersArtifact(
        schema_version="1",
        job_id=tmp_job_dir.name,
        chunker="packing_c",
        embedding_model="rubert_tiny2",
        similarity_threshold=0.7,
        chapters=[
            ChapterItem(
                id="C00",
                start=1,
                end=61,
                source_ids=["s0001"],
                speakers=["A"],
                title="Заголовок главы",
                duration_sec=60,
            )
        ],
        metrics=ChapterMetrics(
            chapters_per_minute=1,
            short_chapters=0,
            long_chapters=0,
        ),
        runtime_sec=1,
    )
    dump_artifact(chapters, tmp_job_dir / "chapters.json")
    completed = {item.stage: item.status for item in plan_job(tmp_job_dir)}
    assert completed["chunk"] == "done"
    assert completed["titles"] == "done"


def test_d1_pln_01_fixture_chain_reports_stages_done(tmp_job_dir: Path) -> None:
    """[D1-PLN-01] after writing audio, speech, turns, transcript, suggestions artifacts, plan reports normalize..correction_suggest as done."""
    from transcriber.models.artifacts import (
        AudioArtifact,
        AudioLoudness,
        AudioNormalized,
        AudioSource,
        SpeechArtifact,
        SuggestionsArtifact,
        TimeInterval,
        TranscriptArtifact,
        TranscriptSegment,
        TurnItem,
        TurnMergeInfo,
        TurnsArtifact,
    )

    # 1. audio.json
    dump_artifact(
        AudioArtifact(
            schema_version="1",
            job_id=tmp_job_dir.name,
            source=AudioSource(filename="audio.wav", size_bytes=1000, duration_sec=5.0),
            normalized=AudioNormalized(path="normalized.wav", sample_rate=16000, channels=1),
            loudness=AudioLoudness(rms_dbfs=-20.0, peak_dbfs=-1.0, gain_db=0.0, gain_applied=False),
            runtime_sec=0.1,
        ),
        tmp_job_dir / "audio.json",
    )

    # 2. speech.json
    dump_artifact(
        SpeechArtifact(
            schema_version="1",
            job_id=tmp_job_dir.name,
            detector="silero",
            fallback_used=False,
            regions=[TimeInterval(start=0.0, end=4.0)],
            speech_sec=4.0,
            runtime_sec=0.1,
        ),
        tmp_job_dir / "speech.json",
    )

    # 3. turns.json
    dump_artifact(
        TurnsArtifact(
            schema_version="1",
            job_id=tmp_job_dir.name,
            diarizer="wespeaker_onnx",
            speaker_count=1,
            turns=[TurnItem(id="t0001", start=0.0, end=4.0, speaker="SPEAKER_00")],
            holes=[],
            merge=TurnMergeInfo(same_speaker_gap_sec=0.3, absorb_shorter_than_sec=1.0),
            runtime_sec=0.1,
        ),
        tmp_job_dir / "turns.json",
    )

    # 4. transcript.json
    dump_artifact(
        TranscriptArtifact(
            schema_version="1",
            job_id=tmp_job_dir.name,
            engine="gigaam_v3_rnnt",
            language="ru",
            segments=[
                TranscriptSegment(
                    id="s0001",
                    turn_id="t0001",
                    start=0.0,
                    end=4.0,
                    speaker="SPEAKER_00",
                    text="Привет",
                    gain_db=0.0,
                    empty=False,
                )
            ],
            holes=[],
            max_segment_sec=25,
            runtime_sec=0.1,
        ),
        tmp_job_dir / "transcript.json",
    )

    # 5. suggestions.json
    dump_artifact(
        SuggestionsArtifact(
            schema_version="1",
            job_id=tmp_job_dir.name,
            dictionaries=[],
            applied=False,
            suggestions=[],
        ),
        tmp_job_dir / "suggestions.json",
    )

    plans = plan_job(tmp_job_dir)
    plan_dict = {p.stage: p.status for p in plans}

    for completed in ["normalize", "vad", "diarize", "asr", "correction_suggest"]:
        assert plan_dict[completed] == "done", f"Stage {completed} was expected to be done"

    for pending_or_unavail in ["chunk", "titles", "insights_extract", "report"]:
        assert plan_dict[pending_or_unavail] in ["pending", "unavailable"]

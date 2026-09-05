"""Тесты планирования стадий конвейера и разрешения статусов."""

from pathlib import Path
import shutil

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

    for stage in CONTRACT_ORDER:
        with pytest.raises(StageNotImplementedError):
            run_stage(stage, tmp_job_dir)

    current_files = set(tmp_job_dir.iterdir())
    assert current_files == initial_files

"""Контрактные тесты упакованных исследовательских артефактов."""

import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from transcriber.models.artifacts import TranscriptArtifact, dump_artifact, load_artifact
from transcriber.models.legacy import convert_legacy_transcript, load_legacy_transcript


@pytest.mark.requires_inputs
def test_d0_fix_01_packed_baseline_transcripts_convert_and_validate(fixtures_dir: Path) -> None:
    """[D0-FIX-01] each packed baseline transcript converts via load_legacy_transcript into valid TranscriptArtifact."""
    baseline_files = [
        fixtures_dir / "artifacts" / "baseline_transformers.json",
        fixtures_dir / "artifacts" / "baseline_ninth.json",
    ]

    for baseline_file in baseline_files:
        assert baseline_file.is_file(), f"Missing fixture file: {baseline_file}"
        artifact = load_legacy_transcript(baseline_file)
        assert isinstance(artifact, TranscriptArtifact)
        assert artifact.schema_version == "1"
        assert len(artifact.segments) > 0

        # Проверка согласованности временных границ
        prev_start = 0.0
        for seg in artifact.segments:
            assert seg.start >= 0.0
            assert seg.end > seg.start
            assert seg.start >= prev_start
            prev_start = seg.start


@pytest.mark.requires_inputs
def test_d0_fix_02_corrupted_copy_fails_cli_validation(fixtures_dir: Path) -> None:
    """[D0-FIX-02] a corrupted copy of a converted artifact (end < start) fails validation with non-zero CLI exit."""
    baseline_file = fixtures_dir / "artifacts" / "baseline_transformers.json"
    artifact = load_legacy_transcript(baseline_file)

    with tempfile.TemporaryDirectory() as tmpdir:
        dest_valid = Path(tmpdir) / "transcript_valid.json"
        dest_corrupt = Path(tmpdir) / "transcript_corrupt.json"

        dump_artifact(artifact, dest_valid)

        # Портим файл: делаем end < start в первом сегменте
        raw_data = json.loads(dest_valid.read_text(encoding="utf-8"))
        raw_data["segments"][0]["end"] = raw_data["segments"][0]["start"] - 1.0
        dest_corrupt.write_text(json.dumps(raw_data), encoding="utf-8")

        # Проверяем валидный файл через CLI
        res_valid = subprocess.run(
            ["uv", "run", "transcriber", "validate", str(dest_valid)],
            capture_output=True,
            text=True,
        )
        assert res_valid.returncode == 0

        # Проверяем поврежденный файл через CLI
        res_corrupt = subprocess.run(
            ["uv", "run", "transcriber", "validate", str(dest_corrupt)],
            capture_output=True,
            text=True,
        )
        assert res_corrupt.returncode != 0


def test_d0_leg_01_legacy_conversion_preserves_fields_and_source_file(tmp_path: Path) -> None:
    """[D0-LEG-01] conversion maps integer id to s0000 ids, preserves text verbatim, marks blank empty=true, leaves source byte-identical."""
    source_data = {
        "audio": "test.m4a",
        "model": "gigaam-v3-rnnt",
        "provider": "gigaam",
        "runtime_sec": 4.5,
        "segments": [
            {"id": 0, "start": 0.0, "end": 2.5, "speaker": "SPEAKER_00", "text": "Привет всем"},
            {"id": 1, "start": 3.0, "end": 5.0, "speaker": "SPEAKER_01", "text": "   "},
        ],
    }
    src_file = tmp_path / "legacy_source.json"
    src_bytes = json.dumps(source_data, indent=2).encode("utf-8")
    src_file.write_bytes(src_bytes)

    dest_file = tmp_path / "transcript.json"
    convert_legacy_transcript(src_file, dest_file)

    # Исходный файл должен остаться побайтово идентичным
    assert src_file.read_bytes() == src_bytes

    # Проверяем сконвертированный артефакт
    artifact = load_artifact(dest_file, TranscriptArtifact)
    assert artifact.segments[0].id == "s0000"
    assert artifact.segments[0].turn_id == "t0000"
    assert artifact.segments[0].text == "Привет всем"
    assert artifact.segments[0].empty is False

    assert artifact.segments[1].id == "s0001"
    assert artifact.segments[1].turn_id == "t0001"
    assert artifact.segments[1].empty is True

"""Integration checks for the packed full-meeting D2 artifact."""

from pathlib import Path

import pytest

from transcriber.config.schema import AppConfig
from transcriber.models.artifacts import ChaptersArtifact, TranscriptArtifact, load_artifact
from transcriber.quality.checks import check_chapters


@pytest.mark.requires_inputs
def test_d2_int_01_full_meeting_chapters_validate(
    fixtures_dir: Path,
    demo_config: AppConfig,
) -> None:
    """[D2-INT-01] Full chapters artifact passes time and coverage gates."""
    transcript_path = fixtures_dir / "artifacts/voice_002/transcript.json"
    chapters_path = Path("cloud_out/artifacts/voice_002/chapters.json")
    if not chapters_path.is_file():
        pytest.skip("D2 gate artifact has not been generated")
    transcript = load_artifact(transcript_path, TranscriptArtifact)
    chapters = load_artifact(chapters_path, ChaptersArtifact)
    report = check_chapters(chapters, transcript, demo_config)
    statuses = {check.id: check.status for check in report.checks}
    assert statuses["G2.1"] == "pass"
    assert statuses["G2.7"] == "pass"

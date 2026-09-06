"""D3 packed-artifact integration gate."""

from pathlib import Path

import pytest

from transcriber.models.artifacts import (
    ChaptersArtifact,
    InsightsArtifact,
    ReportArtifact,
    TranscriptArtifact,
    load_artifact,
)
from transcriber.quality.checks import check_insights, check_report


@pytest.mark.requires_inputs
def test_d3_int_01_packed_outputs_pass_automated_gate(fixtures_dir: Path) -> None:
    """[D3-INT-01] Packed D3 outputs pass G3.1–G3.4 and G3.6–G3.8."""
    output_dir = Path("cloud_out/artifacts/voice_002")
    if not (output_dir / "insights.json").is_file():
        pytest.skip("D3 live artifacts have not been generated")
    transcript = load_artifact(
        fixtures_dir / "artifacts/voice_002/transcript.json", TranscriptArtifact
    )
    chapters = load_artifact(
        fixtures_dir / "artifacts/voice_002/chapters.json", ChaptersArtifact
    )
    insights = load_artifact(output_dir / "insights.json", InsightsArtifact)
    report = load_artifact(output_dir / "report.json", ReportArtifact)
    insights_gate = check_insights(insights, chapters, transcript)
    report_gate = check_report(report, insights, chapters, transcript)
    assert insights_gate.verdict == "pass"
    assert report_gate.verdict in {"pass", "warn"}

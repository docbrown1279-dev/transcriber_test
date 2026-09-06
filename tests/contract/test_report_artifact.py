"""D3 report artifact contract tests."""

from transcriber.models.artifacts import ReportArtifact, load_artifact


def test_d3_art_02_report_fixture_validates_for_demo() -> None:
    """[D3-Q-03] The canonical report fixture validates under the demo profile."""
    artifact = load_artifact(
        "tests/fixtures/artifacts/report.min.json", ReportArtifact
    )
    artifact.validate_for_profile("demo")
    assert artifact.speakers[0].label is None

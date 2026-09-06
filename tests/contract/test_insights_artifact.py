"""D3 insights artifact contract tests."""

from transcriber.models.artifacts import InsightsArtifact, load_artifact


def test_d3_art_01_insights_fixture_validates() -> None:
    """[D3-HYD-01] The canonical insights fixture validates strictly."""
    artifact = load_artifact(
        "tests/fixtures/artifacts/insights.min.json", InsightsArtifact
    )
    assert artifact.chapters[0].key_points[0].src[0].segment_id == "s0003"

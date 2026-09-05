"""Тесты компонента словарных подсказок (dictionary_suggest)."""

from pathlib import Path

from transcriber.config.schema import CorrectionConfig
from transcriber.correction.dictionary_suggest import DictionaryTermSuggester
from transcriber.models.artifacts import (
    TimeInterval,
    TranscriptArtifact,
    TranscriptSegment,
    dump_artifact,
)


def test_d1_dic_01_empty_dictionary_suggestions_applied_false(tmp_path: Path) -> None:
    """[D1-DIC-01] empty dictionary -> suggestions=[], applied=false; transcript bytes unchanged."""
    transcript_file = tmp_path / "transcript.json"
    transcript = TranscriptArtifact(
        schema_version="1",
        job_id="job_dic_test",
        engine="gigaam_v3_rnnt",
        language="ru",
        max_segment_sec=25,
        runtime_sec=1.5,
        segments=[
            TranscriptSegment(
                id="s0001",
                turn_id="t0001",
                speaker="SPEAKER_00",
                start=0.0,
                end=5.0,
                text="Привет мир",
                empty=False,
                gain_db=0.0,
            )
        ],
        holes=[TimeInterval(start=5.0, end=10.0)],
    )
    dump_artifact(transcript, transcript_file)
    original_bytes = transcript_file.read_bytes()

    suggester = DictionaryTermSuggester()
    cfg = CorrectionConfig(mode="suggest_only")
    suggestions = suggester.suggest(transcript=transcript, cfg=cfg)

    # suggestions=[] и applied=false
    assert suggestions.schema_version == "1"
    assert suggestions.job_id == "job_dic_test"
    assert suggestions.dictionaries == []
    assert suggestions.applied is False
    assert suggestions.suggestions == []

    # Байты файла стенограммы не должны измениться
    assert transcript_file.read_bytes() == original_bytes

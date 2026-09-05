"""Словарные подсказки терминов (в profile demo: пустой словарь, только подсказки)."""


from transcriber.config.schema import CorrectionConfig
from transcriber.correction.base import TermSuggester
from transcriber.models.artifacts import SuggestionsArtifact, TranscriptArtifact


class DictionaryTermSuggester(TermSuggester):
    """Компонент словарной подсказки терминов.

    В профиле demo используется пустой базовый словарь:
    формирует suggestions.json с applied=False и пустыми списками,
    никогда не изменяя transcript.json.
    """

    name: str = "dictionary_suggest"

    def suggest(
        self,
        transcript: TranscriptArtifact,
        cfg: CorrectionConfig,
        job_id: str | None = None,
    ) -> SuggestionsArtifact:
        """Формирует артефакт предложений по терминам без изменения стенограммы."""
        resolved_job_id = job_id or transcript.job_id

        return SuggestionsArtifact(
            schema_version="1",
            job_id=resolved_job_id,
            dictionaries=[],
            applied=False,
            suggestions=[],
        )

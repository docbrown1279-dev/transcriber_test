"""Интерфейс (порт) этапа экспорта протоколов встречи."""

from pathlib import Path
from typing import Protocol

from transcriber.models.artifacts import ReportArtifact


class Exporter(Protocol):
    """Протокол экспорта отчета встречи в различные форматы."""

    name: str

    def export(self, report: ReportArtifact, dest: Path) -> Path:
        """Сохраняет отчет в целевой файл заданного формата."""
        ...

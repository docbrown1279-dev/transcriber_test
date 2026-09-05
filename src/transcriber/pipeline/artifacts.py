"""Разрешение путей артефактов в каталоге задачи."""

from pathlib import Path


class JobArtifactPaths:
    """Управление путями к файлам артефактов внутри каталога конкретной задачи."""

    def __init__(self, job_dir: Path | str) -> None:
        self.job_dir = Path(job_dir)

    def path(self, filename: str) -> Path:
        """Возвращает полный путь к файлу артефакта по имени."""
        return self.job_dir / filename

    @property
    def audio(self) -> Path:
        return self.path("audio.json")

    @property
    def speech(self) -> Path:
        return self.path("speech.json")

    @property
    def turns(self) -> Path:
        return self.path("turns.json")

    @property
    def transcript(self) -> Path:
        return self.path("transcript.json")

    @property
    def quality(self) -> Path:
        return self.path("quality.json")

    @property
    def suggestions(self) -> Path:
        return self.path("suggestions.json")

    @property
    def chapters(self) -> Path:
        return self.path("chapters.json")

    @property
    def insights(self) -> Path:
        return self.path("insights.json")

    @property
    def report(self) -> Path:
        return self.path("report.json")

    @property
    def job(self) -> Path:
        return self.path("job.json")

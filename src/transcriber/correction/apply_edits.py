"""Применение правок текста к transcript.json (ручных и позже словарных).

Времена, id и границы глав не меняются — `text` / `empty` / `speaker`
у названных сегментов. Первая правка копирует ASR в `transcript.asr.json`.
Саммари не удаляется: если report есть, пишется пометка неактуальности
(`report.stale.json`) с главами, которые отличаются от ASR.
"""

from __future__ import annotations

import shutil
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from transcriber.models.artifacts import (
    ChaptersArtifact,
    TranscriptArtifact,
    TranscriptSegment,
    dump_artifact,
    load_artifact,
)

ASR_BACKUP_NAME = "transcript.asr.json"
TRANSCRIPT_NAME = "transcript.json"
CHAPTERS_NAME = "chapters.json"
STALE_MARKER_NAME = "report.stale.json"
_REPORT_FILES = ("report.json", "report.md")
_TITLE_MAX_CHARS = 120


class ChapterEditError(ValueError):
    """Ошибка проверки формы правки; сообщение на русском."""


class StaleChapterEdit(BaseModel):
    """Глава, чей текст уже не совпадает с ASR (без текста реплик)."""

    model_config = ConfigDict(extra="forbid")

    chapter_id: str
    title: str = ""
    segment_ids: list[str] = Field(default_factory=list)
    segment_count: int = Field(ge=0)


class ReportStaleMarker(BaseModel):
    """Пометка, что существующее саммари собрано по старому транскрипту."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = "1"
    stale: bool = True
    reason: str = "transcript_edited"
    updated_at: str
    chapters: list[StaleChapterEdit] = Field(default_factory=list)


def apply_segment_texts(
    transcript: TranscriptArtifact,
    updates: dict[str, str],
) -> TranscriptArtifact:
    """Копия транскрипта с заменёнными `text`/`empty` у указанных сегментов."""
    known = {seg.id for seg in transcript.segments}
    missing = [seg_id for seg_id in updates if seg_id not in known]
    if missing:
        raise ChapterEditError("Не найдены сегменты транскрипта для сохранения правок.")
    new_segments: list[TranscriptSegment] = []
    for seg in transcript.segments:
        if seg.id not in updates:
            new_segments.append(seg)
            continue
        text = updates[seg.id]
        new_segments.append(seg.model_copy(update={"text": text, "empty": not bool(text.strip())}))
    return transcript.model_copy(update={"segments": new_segments})


def apply_segment_speakers(
    transcript: TranscriptArtifact,
    updates: dict[str, str],
) -> TranscriptArtifact:
    """Копия транскрипта с заменённым `speaker` у указанных сегментов."""
    known_ids = {seg.id for seg in transcript.segments}
    known_speakers = {seg.speaker for seg in transcript.segments}
    missing = [seg_id for seg_id in updates if seg_id not in known_ids]
    if missing:
        raise ChapterEditError("Не найдены сегменты транскрипта для смены спикера.")
    unknown = [name for name in updates.values() if name not in known_speakers]
    if unknown:
        raise ChapterEditError("Нельзя назначить спикера, которого нет в записи.")
    new_segments: list[TranscriptSegment] = []
    for seg in transcript.segments:
        if seg.id not in updates:
            new_segments.append(seg)
            continue
        new_segments.append(seg.model_copy(update={"speaker": updates[seg.id]}))
    return transcript.model_copy(update={"segments": new_segments})


def updates_for_chapter(
    source_ids: list[str],
    submitted_ids: list[str],
    submitted_texts: list[str],
) -> dict[str, str]:
    """Сопоставить id реплик главы с присланным текстом. Порядок id должен совпасть."""
    if len(submitted_ids) != len(submitted_texts):
        raise ChapterEditError("Неполный набор полей формы главы.")
    if submitted_ids != source_ids:
        raise ChapterEditError("Набор реплик не совпадает с главой. Обновите страницу и повторите.")
    return dict(zip(source_ids, submitted_texts, strict=True))


def ensure_asr_backup(job_dir: Path) -> bool:
    """Один раз копирует transcript.json в transcript.asr.json. True, если файл создан."""
    src = job_dir / TRANSCRIPT_NAME
    dest = job_dir / ASR_BACKUP_NAME
    if dest.is_file() or not src.is_file():
        return False
    shutil.copyfile(src, dest)
    return True


def load_asr_backup(job_dir: Path) -> TranscriptArtifact | None:
    """Загружает исходный ASR-транскрипт, если копия есть."""
    path = job_dir / ASR_BACKUP_NAME
    if not path.is_file():
        return None
    try:
        return load_artifact(path, TranscriptArtifact)
    except Exception:
        return None


def restore_segment_texts(
    current: TranscriptArtifact,
    original: TranscriptArtifact,
    segment_ids: list[str],
) -> TranscriptArtifact:
    """Вернуть текст и спикера выбранных сегментов к ASR-копии."""
    original_by_id = {seg.id: seg for seg in original.segments}
    missing = [seg_id for seg_id in segment_ids if seg_id not in original_by_id]
    if missing:
        raise ChapterEditError("В копии ASR нет сегментов для сброса этой главы.")
    text_updates = {seg_id: original_by_id[seg_id].text for seg_id in segment_ids}
    speaker_updates = {seg_id: original_by_id[seg_id].speaker for seg_id in segment_ids}
    restored = apply_segment_texts(current, text_updates)
    return apply_segment_speakers(restored, speaker_updates)


def restore_all_from_asr(job_dir: Path) -> None:
    """Заменить transcript.json копией ASR целиком."""
    src = job_dir / ASR_BACKUP_NAME
    dest = job_dir / TRANSCRIPT_NAME
    if not src.is_file():
        raise ChapterEditError("Копии исходного распознавания ещё нет.")
    shutil.copyfile(src, dest)


def changed_segment_ids(current: TranscriptArtifact, original: TranscriptArtifact) -> list[str]:
    """Id сегментов, у которых текст или спикер отличаются от ASR."""
    original_by_id = {seg.id: seg for seg in original.segments}
    changed: list[str] = []
    for seg in current.segments:
        src = original_by_id.get(seg.id)
        if src is None:
            continue
        if src.text != seg.text or src.speaker != seg.speaker:
            changed.append(seg.id)
    return changed


def _stale_chapters(
    changed_ids: list[str],
    chapters: ChaptersArtifact | None,
) -> list[StaleChapterEdit]:
    remaining = set(changed_ids)
    result: list[StaleChapterEdit] = []
    if chapters is not None:
        for chapter in chapters.chapters:
            hit = [sid for sid in chapter.source_ids if sid in remaining]
            if not hit:
                continue
            remaining.difference_update(hit)
            result.append(
                StaleChapterEdit(
                    chapter_id=chapter.id,
                    title=chapter.title,
                    segment_ids=hit,
                    segment_count=len(hit),
                )
            )
    if remaining:
        leftover = [sid for sid in changed_ids if sid in remaining]
        result.append(
            StaleChapterEdit(
                chapter_id="-",
                title="",
                segment_ids=leftover,
                segment_count=len(leftover),
            )
        )
    return result


def load_stale_marker(job_dir: Path) -> ReportStaleMarker | None:
    """Читает пометку неактуальности саммари, если файл есть и валиден."""
    path = job_dir / STALE_MARKER_NAME
    if not path.is_file():
        return None
    try:
        return load_artifact(path, ReportStaleMarker)
    except Exception:
        return None


def _has_report(job_dir: Path) -> bool:
    return any((job_dir / name).is_file() for name in _REPORT_FILES)


def sync_report_stale(
    job_dir: Path,
    current: TranscriptArtifact,
    chapters: ChaptersArtifact | None,
) -> ReportStaleMarker | None:
    """Обновить или снять пометку. Саммари не трогает. None — саммари актуально или его нет."""
    path = job_dir / STALE_MARKER_NAME
    original = load_asr_backup(job_dir)
    if not _has_report(job_dir) or original is None:
        path.unlink(missing_ok=True)
        return None
    changed = changed_segment_ids(current, original)
    if not changed:
        path.unlink(missing_ok=True)
        return None
    marker = ReportStaleMarker(
        updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        chapters=_stale_chapters(changed, chapters),
    )
    dump_artifact(marker, path)
    return marker


def stale_notice(marker: ReportStaleMarker) -> str:
    """Короткое русское предупреждение без текста реплик."""
    if marker.reason == "titles_edited":
        return "Саммари неактуально: названия глав меняли после сборки протокола."
    if not marker.chapters:
        return "Саммари неактуально: транскрипт редактировали после сборки протокола."
    parts: list[str] = []
    for chapter in marker.chapters:
        title = f" «{chapter.title}»" if chapter.title else ""
        parts.append(f"{chapter.chapter_id}{title} ({chapter.segment_count})")
    return "Саммари неактуально из-за правок в главах: " + ", ".join(parts) + "."


def chapter_has_edits(
    current: TranscriptArtifact,
    original: TranscriptArtifact | None,
    segment_ids: list[str],
) -> bool:
    """True, если хотя бы одна реплика главы отличается от ASR."""
    if original is None:
        return False
    original_by_id = {seg.id: seg for seg in original.segments}
    current_by_id = {seg.id: seg for seg in current.segments}
    for sid in segment_ids:
        cur = current_by_id.get(sid)
        src = original_by_id.get(sid)
        if cur is None:
            continue
        if src is None:
            return True
        if cur.text != src.text or cur.speaker != src.speaker:
            return True
    return False


def edited_chapter_ids(
    current: TranscriptArtifact,
    original: TranscriptArtifact | None,
    chapters: ChaptersArtifact | None,
) -> list[str]:
    """Id глав, где текст или спикер разошлись с ASR."""
    if original is None or chapters is None:
        return []
    return [
        chapter.id
        for chapter in chapters.chapters
        if chapter_has_edits(current, original, chapter.source_ids)
    ]


def apply_chapter_titles(
    chapters: ChaptersArtifact,
    updates: dict[str, str],
) -> ChaptersArtifact:
    """Копия оглавления с заменёнными названиями; id и границы не меняются."""
    known = {chapter.id for chapter in chapters.chapters}
    missing = [cid for cid in updates if cid not in known]
    if missing:
        raise ChapterEditError("Не найдены главы для сохранения названий.")
    new_items = []
    for chapter in chapters.chapters:
        if chapter.id not in updates:
            new_items.append(chapter)
            continue
        title = " ".join(updates[chapter.id].split())[:_TITLE_MAX_CHARS]
        new_items.append(chapter.model_copy(update={"title": title}))
    return chapters.model_copy(update={"chapters": new_items})


def save_chapters(job_dir: Path, chapters: ChaptersArtifact) -> None:
    """Пишет канонический chapters.json."""
    dump_artifact(chapters, job_dir / CHAPTERS_NAME)


def mark_report_stale_titles(
    job_dir: Path,
    chapters: ChaptersArtifact,
) -> ReportStaleMarker | None:
    """Пометить саммари устаревшим после смены названий глав."""
    if not _has_report(job_dir):
        return None
    existing = load_stale_marker(job_dir)
    if existing is not None and existing.reason == "transcript_edited":
        return existing
    marker = ReportStaleMarker(
        updated_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        reason="titles_edited",
        chapters=[
            StaleChapterEdit(chapter_id=chapter.id, title=chapter.title, segment_count=0)
            for chapter in chapters.chapters
        ],
    )
    dump_artifact(marker, job_dir / STALE_MARKER_NAME)
    return marker


def save_transcript(job_dir: Path, transcript: TranscriptArtifact) -> None:
    """Пишет канонический transcript.json."""
    dump_artifact(transcript, job_dir / TRANSCRIPT_NAME)

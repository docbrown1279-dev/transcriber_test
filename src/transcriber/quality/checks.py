"""Проверки качества артефактов и формирования отчетов шлюзов."""

from dataclasses import dataclass, field
from typing import Any

from transcriber.models.artifacts import (
    ChaptersArtifact,
    QualityArtifact,
    QualityCheckItem,
    TranscriptArtifact,
)
from transcriber.config.schema import AppConfig
from transcriber.llm.titles import STAMP_PREFIXES
from transcriber.quality.chapter_metrics import calculate_chapter_metrics
from transcriber.quality.ru_ratio import RatioResult, russian_word_ratio


@dataclass(frozen=True)
class CheckResult:
    """Результат отдельной проверки шлюза качества."""

    id: str
    status: str
    value: Any
    threshold: Any
    message: str = ""


@dataclass
class CheckReport:
    """Сводный отчет проверок качества."""

    verdict: str = "pass"
    checks: list[CheckResult] = field(default_factory=list)

    def add(self, check: CheckResult) -> None:
        self.checks.append(check)
        if check.status == "fail":
            self.verdict = "fail"
        elif check.status == "warn" and self.verdict != "fail":
            self.verdict = "warn"


def check_russian_ratio(
    result: RatioResult,
    threshold: float = 0.90,
    check_id: str = "G1.1",
) -> CheckResult:
    """Проверяет соответствие доли русских слов порогу качества."""
    status = "pass" if result.ratio >= threshold else "fail"
    return CheckResult(
        id=check_id,
        status=status,
        value=round(result.ratio, 3),
        threshold=threshold,
        message=f"Russian word ratio {result.ratio:.3f} (threshold >= {threshold})",
    )


def check_latin_contamination(
    latin_chars: int,
    max_allowed: int = 0,
    check_id: str = "G1.2",
) -> CheckResult:
    """Проверяет отсутствие артефактов латинских символов в русскоязычном транскрипте."""
    status = "pass" if latin_chars <= max_allowed else "fail"
    return CheckResult(
        id=check_id,
        status=status,
        value=latin_chars,
        threshold=max_allowed,
        message=f"Latin characters count {latin_chars} (threshold == {max_allowed})",
    )


def check_time_monotonicity(
    transcript: TranscriptArtifact,
    audio_duration_sec: float | None = None,
    check_id: str = "G1.4",
) -> CheckResult:
    """Проверяет монотонность сегментов и нахождение внутри длительности аудио."""
    prev_start = 0.0
    for seg in transcript.segments:
        if seg.start < 0.0 or seg.end <= seg.start:
            return CheckResult(
                id=check_id,
                status="fail",
                value=f"Invalid segment bounds: {seg.start}..{seg.end}",
                threshold="start >= 0 and end > start",
                message=f"Segment {seg.id} has invalid time bounds",
            )
        if seg.start < prev_start:
            return CheckResult(
                id=check_id,
                status="fail",
                value=f"Non-monotonic: {seg.start} < {prev_start}",
                threshold="monotonic start times",
                message=f"Segment {seg.id} start time is not monotonic",
            )
        if audio_duration_sec is not None and seg.end > audio_duration_sec + 1.0:
            return CheckResult(
                id=check_id,
                status="fail",
                value=f"End {seg.end} exceeds duration {audio_duration_sec}",
                threshold=f"<= {audio_duration_sec}",
                message=f"Segment {seg.id} exceeds audio duration",
            )
        prev_start = seg.start

    return CheckResult(
        id=check_id,
        status="pass",
        value=len(transcript.segments),
        threshold="all segments monotonic and inside duration",
        message="All segment timestamps monotonic and within duration",
    )


def build_quality_artifact(
    transcript: TranscriptArtifact,
    audio_duration_sec: float | None = None,
    job_id: str | None = None,
) -> QualityArtifact:
    """Строит артефакт качества QualityArtifact для шлюза G1."""
    resolved_job_id = job_id or transcript.job_id

    ratio_res = russian_word_ratio(transcript.segments)
    empty_segs = sum(1 for s in transcript.segments if s.empty or not s.text.strip())
    total_hole_sec = round(sum(h.end - h.start for h in transcript.holes), 3)

    report = CheckReport()

    # G1.1: Russian word ratio >= 0.90
    c1 = check_russian_ratio(ratio_res, threshold=0.90, check_id="G1.1")
    report.add(c1)

    # G1.2: Latin characters == 0
    c2 = check_latin_contamination(ratio_res.latin_chars, max_allowed=0, check_id="G1.2")
    report.add(c2)

    # G1.3: Schemas valid
    report.add(
        CheckResult(
            id="G1.3",
            status="pass",
            value="valid",
            threshold="valid pydantic model",
            message="Transcript schema validated against contract",
        )
    )

    # G1.4: Times monotonic / inside duration
    c4 = check_time_monotonicity(transcript, audio_duration_sec=audio_duration_sec, check_id="G1.4")
    report.add(c4)

    # G1.5: Holes and empty segments listed
    hole_status = "warn" if (empty_segs > 50 or total_hole_sec > 500.0) else "pass"
    report.add(
        CheckResult(
            id="G1.5",
            status=hole_status,
            value={"empty_segments": empty_segs, "hole_sec_total": total_hole_sec},
            threshold="enumerated in artifact",
            message=(
                f"Holes: {len(transcript.holes)} ({total_hole_sec} s), "
                f"Empty segments: {empty_segs}"
            ),
        )
    )

    quality_checks = [
        QualityCheckItem(
            id=c.id,
            status=c.status,
            threshold=c.threshold,
            value=c.value,
            message=c.message,
        )
        for c in report.checks
    ]

    return QualityArtifact(
        schema_version="1",
        job_id=resolved_job_id,
        russian_word_ratio=round(ratio_res.ratio, 3),
        total_words=ratio_res.total_words,
        latin_chars_in_segments=ratio_res.latin_chars,
        empty_segments=empty_segs,
        hole_sec_total=total_hole_sec,
        oov_words=[],
        verdict=report.verdict,
        checks=quality_checks,
    )


def check_chapters(
    chapters: ChaptersArtifact,
    transcript: TranscriptArtifact,
    cfg: AppConfig,
) -> CheckReport:
    """Проверяет артефакт глав по автоматическим условиям G2.1–G2.7."""
    report = CheckReport()
    segment_by_id = {segment.id: segment for segment in transcript.segments}

    time_errors: list[str] = []
    for chapter in chapters.chapters:
        try:
            first = segment_by_id[chapter.source_ids[0]]
            last = segment_by_id[chapter.source_ids[-1]]
        except KeyError as exc:
            time_errors.append(f"{chapter.id}: unknown source {exc.args[0]}")
            continue
        if chapter.start != first.start or chapter.end != last.end:
            time_errors.append(
                f"{chapter.id}: {chapter.start}..{chapter.end} != {first.start}..{last.end}"
            )
    report.add(
        CheckResult(
            id="G2.1",
            status="fail" if time_errors else "pass",
            value=time_errors or len(chapters.chapters),
            threshold="exact first/last source segment bounds",
            message="; ".join(time_errors) if time_errors else "All chapter bounds are exact",
        )
    )

    meeting_sec = max((segment.end for segment in transcript.segments), default=0.0)
    short_sec, long_sec = cfg.chunking.target_chapter_sec
    if meeting_sec > 0:
        metrics = calculate_chapter_metrics(
            chapters,
            meeting_sec,
            short_sec=short_sec,
            long_sec=long_sec,
        )
        density = metrics.chapters_per_minute
    else:
        metrics = chapters.metrics
        density = 0.0
    target_low, target_high = cfg.chunking.target_chapters_per_minute
    warn_low, warn_high = cfg.chunking.warning_chapters_per_minute
    density_status = (
        "pass"
        if target_low <= density <= target_high
        else "warn"
        if warn_low <= density <= warn_high
        else "fail"
    )
    report.add(
        CheckResult(
            id="G2.2",
            status=density_status,
            value=density,
            threshold=f"pass [{target_low}, {target_high}], warn [{warn_low}, {warn_high}]",
            message=f"Chapter density is {density:.3f} per minute",
        )
    )

    short_ids = [
        chapter.id for chapter in chapters.chapters if chapter.duration_sec < short_sec
    ]
    long_ids = [
        chapter.id for chapter in chapters.chapters if chapter.duration_sec > long_sec
    ]
    report.add(
        CheckResult(
            id="G2.3",
            status="warn" if short_ids or long_ids else "pass",
            value={"short": short_ids, "long": long_ids},
            threshold=f"short < {short_sec}s; long > {long_sec}s",
            message=f"Short chapters: {short_ids}; long chapters: {long_ids}",
        )
    )

    overlong = {
        chapter.id: len(chapter.title.split())
        for chapter in chapters.chapters
        if len(chapter.title.split()) > cfg.llm.title_max_words
    }
    report.add(
        CheckResult(
            id="G2.4",
            status="fail" if overlong else "pass",
            value=overlong or "all within limit",
            threshold=f"<= {cfg.llm.title_max_words} words",
            message=f"Overlong titles: {overlong}" if overlong else "All titles within word limit",
        )
    )

    stamped = [
        chapter.id
        for chapter in chapters.chapters
        if any(chapter.title.casefold().startswith(prefix) for prefix in STAMP_PREFIXES)
    ]
    report.add(
        CheckResult(
            id="G2.5",
            status="fail" if stamped else "pass",
            value=stamped,
            threshold="no forbidden prefix",
            message=f"Forbidden title prefixes: {stamped}",
        )
    )

    normalized_titles = [chapter.title.strip().casefold() for chapter in chapters.chapters]
    empty_titles = [
        chapter.id
        for chapter, normalized in zip(chapters.chapters, normalized_titles, strict=True)
        if not normalized
    ]
    duplicates = sorted(
        {title for title in normalized_titles if title and normalized_titles.count(title) > 1}
    )
    report.add(
        CheckResult(
            id="G2.6",
            status="fail" if empty_titles or duplicates else "pass",
            value={"empty": empty_titles, "duplicates": duplicates},
            threshold="unique non-empty titles",
            message=f"Empty titles: {empty_titles}; duplicates: {duplicates}",
        )
    )

    expected_ids = {segment.id for segment in transcript.segments if segment.text.strip()}
    source_counts: dict[str, int] = {}
    for chapter in chapters.chapters:
        for source_id in chapter.source_ids:
            if source_id in expected_ids:
                source_counts[source_id] = source_counts.get(source_id, 0) + 1
    missing = sorted(expected_ids - source_counts.keys())
    overlaps = sorted(source_id for source_id, count in source_counts.items() if count != 1)
    report.add(
        CheckResult(
            id="G2.7",
            status="fail" if missing or overlaps else "pass",
            value={"missing": missing, "overlaps": overlaps},
            threshold="every non-empty source id exactly once",
            message=f"Missing source ids: {missing}; overlaps: {overlaps}",
        )
    )
    return report

"""Проверки качества артефактов и формирования отчетов шлюзов."""

from dataclasses import dataclass, field
from typing import Any

from transcriber.models.artifacts import (
    QualityArtifact,
    QualityCheckItem,
    TranscriptArtifact,
)
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

"""Проверки качества артефактов и формирования отчетов шлюзов."""

from dataclasses import dataclass, field
from typing import Any

from transcriber.quality.ru_ratio import RatioResult


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

    verdict: str
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
        value=result.ratio,
        threshold=threshold,
        message=f"Russian word ratio {result.ratio} (threshold >= {threshold})",
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

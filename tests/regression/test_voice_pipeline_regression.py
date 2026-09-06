"""Soft regression: full speech chain on data/test_voice.m4a.

Failures are WARN + report (manual review). They do **not** fail the default pytest
gate unless REGRESSION_STRICT=1.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pytest

from transcriber.models.artifacts import (
    SpeechArtifact,
    TranscriptArtifact,
    TurnsArtifact,
    load_artifact,
)
from transcriber.pipeline.orchestrator import run_job
from transcriber.quality.intervals import speech_regions_iou
from transcriber.quality.ru_ratio import russian_word_ratio

REPO = Path(__file__).resolve().parents[2]
REF_PATH = REPO / "tests" / "fixtures" / "regression" / "test_voice_ref.json"
AUDIO_CANDIDATES = (
    REPO / "data" / "test_voice.m4a",
    REPO / "cloud_in" / "inputs" / "audio" / "test_voice.m4a",
)
REPORT_PATH = REPO / "agent_docs" / "reports" / "regression_test_voice.md"


@dataclass
class CheckResult:
    id: str
    ok: bool
    detail: str


@dataclass
class RegressionReport:
    verdict: str
    checks: list[CheckResult] = field(default_factory=list)
    job_dir: str = ""

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks)


def _resolve_audio() -> Path:
    for path in AUDIO_CANDIDATES:
        if path.is_file():
            return path
    pytest.skip(f"test_voice.m4a not found in {AUDIO_CANDIDATES}")


def _write_report(report: RegressionReport) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Regression — test_voice pipeline",
        "",
        f"**Verdict:** `{report.verdict}`",
        "",
        "Soft gate: FAIL here means **manual review required**, not an automatic merge block.",
        "",
        f"Job dir: `{report.job_dir}`",
        "",
        "| id | ok | detail |",
        "|---|---|---|",
    ]
    for check in report.checks:
        lines.append(f"| {check.id} | {check.ok} | {check.detail} |")
    lines.append("")
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


@pytest.mark.regression
@pytest.mark.slow
def test_reg_voice_pipeline_soft(tmp_path: Path) -> None:
    """[REG-VOICE-01] VAD IoU + speaker band + RU ASR on test_voice (soft)."""
    if not (REPO / "models" / "silero_vad.onnx").is_file():
        pytest.skip("models/silero_vad.onnx missing")

    ref = json.loads(REF_PATH.read_text(encoding="utf-8"))
    audio = _resolve_audio()
    job_dir = tmp_path / "reg_test_voice"
    run_job(job_dir=job_dir, source_audio=audio, until="asr")

    speech = load_artifact(job_dir / "speech.json", SpeechArtifact)
    turns = load_artifact(job_dir / "turns.json", TurnsArtifact)
    transcript = load_artifact(job_dir / "transcript.json", TranscriptArtifact)

    ref_regions = [(r["start"], r["end"]) for r in ref["vad"]["regions"]]
    hyp_regions = [(r.start, r.end) for r in speech.regions]
    iou = speech_regions_iou(ref_regions, hyp_regions)
    min_iou = float(ref["vad"]["min_iou"])

    sp_min = int(ref["diarization"]["speakers_min"])
    sp_max = int(ref["diarization"]["speakers_max"])
    speakers = int(turns.speaker_count)

    ratio = russian_word_ratio(transcript.segments)
    min_ru = float(ref["asr"]["min_russian_word_ratio"])
    max_latin = int(ref["asr"]["max_latin_chars"])

    checks = [
        CheckResult(
            id="REG.VAD.IoU",
            ok=iou >= min_iou,
            detail=f"iou={iou:.3f} threshold>={min_iou:.3f} hyp_regions={len(hyp_regions)}",
        ),
        CheckResult(
            id="REG.DIAR.speakers",
            ok=sp_min <= speakers <= sp_max,
            detail=f"speaker_count={speakers} band=[{sp_min},{sp_max}]",
        ),
        CheckResult(
            id="REG.ASR.ru_ratio",
            ok=ratio.ratio >= min_ru,
            detail=f"russian_word_ratio={ratio.ratio:.3f} threshold>={min_ru:.3f} words={ratio.total_words}",
        ),
        CheckResult(
            id="REG.ASR.latin",
            ok=ratio.latin_chars <= max_latin,
            detail=f"latin_chars={ratio.latin_chars} max={max_latin}",
        ),
    ]
    report = RegressionReport(
        verdict="PASS" if all(c.ok for c in checks) else "WARN_MANUAL_REVIEW",
        checks=checks,
        job_dir=str(job_dir),
    )
    _write_report(report)

    # Machine-readable companion next to markdown
    (REPORT_PATH.with_suffix(".json")).write_text(
        json.dumps(
            {
                "verdict": report.verdict,
                "checks": [asdict(c) for c in checks],
                "job_dir": report.job_dir,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    if report.ok:
        return

    message = (
        "test_voice regression WARN — manual review required: "
        + "; ".join(f"{c.id}: {c.detail}" for c in checks if not c.ok)
        + f" (see {REPORT_PATH})"
    )
    warnings.warn(message, stacklevel=1)
    if os.environ.get("REGRESSION_STRICT", "").strip() in {"1", "true", "TRUE", "yes"}:
        pytest.fail(message)
    # Soft: do not fail the default gate

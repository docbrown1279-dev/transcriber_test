"""Конвертация research JSON (legacy) в канонический TranscriptArtifact."""

from __future__ import annotations

import json
from pathlib import Path

from transcriber.models.artifacts import TranscriptArtifact, TranscriptSegment, dump_artifact


def load_legacy_transcript(path: Path | str, *, job_id: str = "legacy") -> TranscriptArtifact:
    """Читает research transcript и возвращает канонический артефакт."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    engine = str(raw.get("model") or raw.get("engine") or "unknown")
    provider = raw.get("provider")
    if provider and provider not in engine:
        engine = f"{engine}/{provider}"

    segments: list[TranscriptSegment] = []
    for item in raw.get("segments") or []:
        seg_id = item.get("id")
        if isinstance(seg_id, int):
            sid = f"s{seg_id:04d}"
        else:
            sid = str(seg_id)
        text = str(item.get("text") or "")
        start = float(item["start"])
        end = float(item["end"])
        segments.append(
            TranscriptSegment(
                id=sid,
                turn_id=str(item.get("turn_id") or f"t{sid[1:]}"),
                start=start,
                end=end,
                speaker=str(item.get("speaker") or "SPEECH"),
                text=text,
                gain_db=float(item.get("gain_db") or 0.0),
                empty=not bool(text.strip()),
            )
        )

    return TranscriptArtifact(
        schema_version="1",
        job_id=job_id,
        engine=engine,
        language=str(raw.get("language") or "ru"),
        segments=segments,
        holes=[],
        max_segment_sec=float(raw.get("max_segment_sec") or 25),
        runtime_sec=float(raw.get("runtime_sec") or 0.0),
    )


def convert_legacy_transcript(src: Path | str, dest: Path | str) -> TranscriptArtifact:
    """Конвертирует legacy JSON в файл канонического артефакта."""
    artifact = load_legacy_transcript(src)
    dump_artifact(artifact, dest)
    return artifact

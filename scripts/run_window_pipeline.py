#!/usr/bin/env python3
"""Run full speech pipeline (normalize→…→ASR) on the 10 tune windows.

Uses dual-path from config (vad_input compress + ASR on normalized + per-turn gain).
Writes eval/d1/partial_windows_dual/ and agent_docs/reports/d1_window_pipeline.md.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from tune_silero_vad import WINDOWS, VOICE  # noqa: E402

from transcriber.models.artifacts import TranscriptArtifact, load_artifact  # noqa: E402
from transcriber.pipeline.orchestrator import run_job  # noqa: E402

OUT = ROOT / "eval" / "d1" / "partial_windows_dual"
GOLD_DIR = ROOT / "eval" / "d1" / "transcribe"


def extract_wav(src: Path, start: float, end: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            f"{start:.3f}",
            "-to",
            f"{end:.3f}",
            "-i",
            str(src),
            "-ar",
            "16000",
            "-ac",
            "1",
            str(dest),
        ],
        check=True,
    )


def gold_text_in_window(clip: str, start: float, end: float) -> list[dict]:
    path = GOLD_DIR / f"{clip}.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    segs = data.get("segments") or data.get("turns") or []
    out = []
    for s in segs:
        s0 = float(s.get("start", 0))
        s1 = float(s.get("end", 0))
        if max(0.0, min(end, s1) - max(start, s0)) > 0.05:
            out.append(
                {
                    "id": s.get("id"),
                    "start": s0,
                    "end": s1,
                    "speaker": s.get("speaker"),
                    "text": (s.get("text") or "").strip(),
                }
            )
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    summary: list[dict] = []

    for i, win in enumerate(WINDOWS, start=1):
        print(f"[{i}/{len(WINDOWS)}] {win.kind} {win.name} …", flush=True)
        src = VOICE / win.clip / f"{win.clip}_full.wav"
        job_dir = OUT / "jobs" / win.name
        if job_dir.exists():
            # fresh job dir
            import shutil

            shutil.rmtree(job_dir)
        job_dir.mkdir(parents=True)
        wav = job_dir / "window.wav"
        extract_wav(src, win.start, win.end, wav)

        run_job(job_dir=job_dir, source_audio=wav, until="correction_suggest")
        tr = load_artifact(job_dir / "transcript.json", TranscriptArtifact)
        speech = json.loads((job_dir / "speech.json").read_text(encoding="utf-8"))
        audio = json.loads((job_dir / "audio.json").read_text(encoding="utf-8"))

        texts = [s.text for s in tr.segments if (s.text or "").strip()]
        gold = gold_text_in_window(win.clip, win.start, win.end)
        gold_joined = " | ".join(g["text"] for g in gold if g["text"])
        hyp_joined = " | ".join(texts)

        row = {
            "window": win.name,
            "kind": win.kind,
            "clip": win.clip,
            "note": win.note,
            "vad_applied": audio.get("vad_input", {}).get("applied"),
            "vad_filter": audio.get("vad_input", {}).get("filter"),
            "speech_sec": speech.get("speech_sec"),
            "n_regions": len(speech.get("regions") or []),
            "n_asr_segments": len(tr.segments),
            "n_nonempty": len(texts),
            "hyp_text": hyp_joined,
            "gold_text": gold_joined,
            "runtime_asr_sec": tr.runtime_sec,
        }
        summary.append(row)
        (job_dir / "compare.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            f"  speech={row['speech_sec']:.1f}s nonempty={row['n_nonempty']} "
            f"hyp[:80]={hyp_joined[:80]!r}",
            flush=True,
        )

    (OUT / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        "# Window pipeline (dual-path) — eval/d1/partial_windows_dual",
        "",
        "Partial smoke only (10 short windows), not a numbered human-eval attempt.",
        "Full chain normalize→VAD(dynaudnorm)→diarize→ASR(GigaAM, per-turn gain) "
        "on the same 10 windows as Silero/compressor tunes.",
        "",
        "## Results",
        "",
    ]
    for row in summary:
        lines.append(f"### `{row['window']}` ({row['kind']})")
        lines.append("")
        lines.append(
            f"- speech_sec={row['speech_sec']}, regions={row['n_regions']}, "
            f"ASR nonempty={row['n_nonempty']}/{row['n_asr_segments']}"
        )
        lines.append(f"- **gold:** {row['gold_text'][:300]}")
        lines.append(f"- **hyp:** {row['hyp_text'][:300] or '*(empty)*'}")
        lines.append("")

    rescue_ok = sum(
        1 for r in summary if r["kind"] == "rescue" and r["n_nonempty"] > 0
    )
    rescue_n = sum(1 for r in summary if r["kind"] == "rescue")
    reg_ok = sum(
        1 for r in summary if r["kind"] == "regression" and r["n_nonempty"] > 0
    )
    reg_n = sum(1 for r in summary if r["kind"] == "regression")
    lines.extend(
        [
            "## Verdict",
            "",
            f"- Rescue windows with some ASR text: **{rescue_ok}/{rescue_n}** "
            "(attempt 3 had missing_hyp on these).",
            f"- Regression windows with ASR text: **{reg_ok}/{reg_n}**.",
            "- Next: if rescue recovers readable phrases → keep dual-path and run full meeting.",
            "",
        ]
    )
    text = "\n".join(lines)
    (OUT / "notes.md").write_text(text, encoding="utf-8")
    report = ROOT / "agent_docs" / "reports" / "d1_window_pipeline.md"
    report.write_text(text, encoding="utf-8")
    print(f"Wrote {report}", flush=True)


if __name__ == "__main__":
    main()

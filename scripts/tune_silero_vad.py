#!/usr/bin/env python3
"""Silero VAD threshold grid on short eval windows (rescue + regression).

Writes eval/d1/4/silero_tune.md and JSON rows under eval/d1/4/.
Does not modify production config values — only measures coverage.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path

from transcriber.config.schema import VadConfig
from transcriber.vad.silero import SileroVadDetector

ROOT = Path(__file__).resolve().parents[1]
VOICE = ROOT / "eval" / "d1" / "voice"
OUT = ROOT / "eval" / "d1" / "4"


@dataclass(frozen=True)
class Window:
    clip: str
    kind: str  # rescue | regression
    name: str
    start: float
    end: float
    note: str


# 5 rescue (missing_hyp / VAD_HOLE in attempt 3) + 5 regression (human-good)
WINDOWS: list[Window] = [
    Window("test_voice", "rescue", "voice_start", 0.0, 13.0, "gold 0–13 missing"),
    Window("test_voice", "rescue", "voice_long_b", 22.0, 64.0, "gold id=5 ~42s hole"),
    Window("test_apartments", "rescue", "apt_open", 0.0, 5.0, "gold id=0 missing"),
    Window("test_apartments", "rescue", "apt_b_block", 26.0, 53.5, "gold B 26–53 missing"),
    Window("test_transformers", "rescue", "xfmr_tail", 33.0, 85.0, "gold B 33–85 missing"),
    Window("test_apartments", "regression", "apt_flats", 5.5, 14.5, "human-good apartments Q"),
    Window("test_apartments", "regression", "apt_rooms", 71.0, 80.0, "human-good rooms"),
    Window("test_ninth", "regression", "ninth_ready", 19.5, 22.5, "human-good ready?"),
    Window("test_ninth", "regression", "ninth_send", 40.5, 50.0, "human-good send plans"),
    Window("test_ninth", "regression", "ninth_market", 55.0, 64.0, "human-good квартирография"),
]

VARIANTS: dict[str, dict[str, float | int]] = {
    "B0": {"threshold": 0.5, "neg_threshold": 0.35, "min_speech_ms": 200, "min_silence_ms": 200},
    "B1": {"threshold": 0.35, "neg_threshold": 0.20, "min_speech_ms": 200, "min_silence_ms": 200},
    "B2": {"threshold": 0.25, "neg_threshold": 0.15, "min_speech_ms": 200, "min_silence_ms": 200},
}


def overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def extract_wav(src: Path, start: float, end: float, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
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
    ]
    subprocess.run(cmd, check=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    detector = SileroVadDetector()
    rows: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="silero_tune_") as tmp:
        tmp_path = Path(tmp)
        for win in WINDOWS:
            src = VOICE / win.clip / f"{win.clip}_full.wav"
            if not src.is_file():
                raise FileNotFoundError(src)
            clip_wav = tmp_path / f"{win.name}.wav"
            extract_wav(src, win.start, win.end, clip_wav)
            win_dur = win.end - win.start

            for vid, params in VARIANTS.items():
                cfg = VadConfig(
                    engine="silero",
                    threshold=float(params["threshold"]),
                    neg_threshold=float(params["neg_threshold"]),
                    min_speech_ms=int(params["min_speech_ms"]),
                    min_silence_ms=int(params["min_silence_ms"]),
                    fallback="disabled",
                )
                # detect writes speech.json next to wav — use per-variant dir
                work = tmp_path / f"{win.name}_{vid}"
                work.mkdir(exist_ok=True)
                local_wav = work / "audio.wav"
                local_wav.write_bytes(clip_wav.read_bytes())
                art = detector.detect(local_wav, cfg, job_id=f"{win.name}_{vid}")
                speech_sec = float(art.speech_sec)
                cover = speech_sec / win_dur if win_dur > 0 else 0.0
                regions = [{"start": r.start, "end": r.end} for r in art.regions]
                rows.append(
                    {
                        "variant": vid,
                        "kind": win.kind,
                        "window": win.name,
                        "clip": win.clip,
                        "start": win.start,
                        "end": win.end,
                        "note": win.note,
                        "window_sec": round(win_dur, 3),
                        "speech_sec": speech_sec,
                        "cover": round(cover, 4),
                        "n_regions": len(regions),
                        "regions": regions,
                        "params": params,
                    }
                )

    (OUT / "silero_tune_rows.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # Markdown summary
    lines = [
        "# Silero VAD tune — eval/d1/4",
        "",
        "Grid: B0 (baseline 0.5/0.35), B1 (0.35/0.20), B2 (0.25/0.15). "
        "`min_speech_ms`=`min_silence_ms`=200.",
        "",
        "## Coverage (speech_sec / window)",
        "",
        "| kind | window | B0 | B1 | B2 | note |",
        "|---|---|---:|---:|---:|---|",
    ]
    by_win: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_win.setdefault(r["window"], {})[r["variant"]] = r
    for win in WINDOWS:
        b = by_win[win.name]
        lines.append(
            f"| {win.kind} | `{win.name}` | "
            f"{b['B0']['cover']:.2%} | {b['B1']['cover']:.2%} | {b['B2']['cover']:.2%} | "
            f"{win.note} |"
        )

    lines.extend(["", "## Rescue delta vs B0 (cover)", ""])
    for win in WINDOWS:
        if win.kind != "rescue":
            continue
        b = by_win[win.name]
        d1 = b["B1"]["cover"] - b["B0"]["cover"]
        d2 = b["B2"]["cover"] - b["B0"]["cover"]
        lines.append(f"- `{win.name}`: B1 {d1:+.1%}, B2 {d2:+.1%} (B0={b['B0']['cover']:.1%})")

    lines.extend(["", "## Regression delta vs B0 (cover)", ""])
    for win in WINDOWS:
        if win.kind != "regression":
            continue
        b = by_win[win.name]
        d1 = b["B1"]["cover"] - b["B0"]["cover"]
        d2 = b["B2"]["cover"] - b["B0"]["cover"]
        flag = ""
        if d1 < -0.05 or d2 < -0.05:
            flag = " **WARN drop>5pp**"
        lines.append(
            f"- `{win.name}`: B1 {d1:+.1%}, B2 {d2:+.1%} (B0={b['B0']['cover']:.1%}){flag}"
        )

    lines.extend(
        [
            "",
            "## Next",
            "",
            "If rescue cover rises without regression WARN: pick B1 or B2 into `config/base.yaml` "
            "`vad.*`, re-check with ASR smoke on new regions.",
            "",
        ]
    )
    (OUT / "silero_tune.md").write_text("\n".join(lines), encoding="utf-8")
    # Trackable copy (eval/ is gitignored)
    report = ROOT / "agent_docs" / "reports" / "d1_silero_tune.md"
    report.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT / 'silero_tune.md'} and {report}")


if __name__ == "__main__":
    main()

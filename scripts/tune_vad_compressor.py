#!/usr/bin/env python3
"""VAD-only preprocess A/B: light compressor on same windows as Silero tune.

ASR path is NOT touched — this measures Silero cover on vad_input-style audio only.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from tune_silero_vad import WINDOWS, OUT, VOICE, extract_wav
from transcriber.config.schema import VadConfig
from transcriber.vad.silero import SileroVadDetector

ROOT = Path(__file__).resolve().parents[1]

# ffmpeg af chains for VAD input only (not for ASR)
PRESETS: dict[str, str | None] = {
    "C0_raw": None,
    # threshold≈-30 dBFS (0.0316), ratio 4, makeup ≈ +12 dB (×4)
    "C1_comp_light": (
        "acompressor=threshold=0.031622776:ratio=4:attack=20:release=200:"
        "makeup=4:knee=2.828:detection=rms"
    ),
    # stronger makeup after same compressor
    "C2_comp_hot": (
        "acompressor=threshold=0.031622776:ratio=6:attack=15:release=250:"
        "makeup=8:knee=2.828:detection=rms,alimiter=limit=0.89"
    ),
    # dynamic normalizer (more aggressive leveling)
    "C3_dynaudnorm": "dynaudnorm=f=150:g=7:p=0.9",
}

VAD = VadConfig(
    engine="silero",
    threshold=0.5,
    neg_threshold=0.35,
    min_speech_ms=200,
    min_silence_ms=200,
    fallback="disabled",
)


def apply_af(src: Path, dest: Path, af: str | None) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-ar", "16000", "-ac", "1"]
    if af:
        cmd.extend(["-af", af])
    cmd.append(str(dest))
    subprocess.run(cmd, check=True)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    detector = SileroVadDetector()
    rows: list[dict] = []

    with tempfile.TemporaryDirectory(prefix="vad_comp_") as tmp:
        tmp_path = Path(tmp)
        for win in WINDOWS:
            src = VOICE / win.clip / f"{win.clip}_full.wav"
            raw = tmp_path / f"{win.name}_raw.wav"
            extract_wav(src, win.start, win.end, raw)
            win_dur = win.end - win.start

            for pid, af in PRESETS.items():
                work = tmp_path / f"{win.name}_{pid}"
                work.mkdir(exist_ok=True)
                wav = work / "audio.wav"
                apply_af(raw, wav, af)
                art = detector.detect(wav, VAD, job_id=f"{win.name}_{pid}")
                cover = float(art.speech_sec) / win_dur if win_dur > 0 else 0.0
                rows.append(
                    {
                        "preset": pid,
                        "kind": win.kind,
                        "window": win.name,
                        "clip": win.clip,
                        "note": win.note,
                        "window_sec": round(win_dur, 3),
                        "speech_sec": float(art.speech_sec),
                        "cover": round(cover, 4),
                        "n_regions": len(art.regions),
                        "regions": [{"start": r.start, "end": r.end} for r in art.regions],
                        "af": af,
                    }
                )

    (OUT / "vad_compressor_rows.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    by_win: dict[str, dict[str, dict]] = {}
    for r in rows:
        by_win.setdefault(r["window"], {})[r["preset"]] = r

    presets = list(PRESETS.keys())
    lines = [
        "# VAD compressor A/B — eval/d1/4",
        "",
        "Same 5 rescue + 5 regression windows as Silero tune. Silero thresholds = B0 (0.5/0.35).",
        "Audio filter applied **only** for VAD input (simulates `vad_input.wav`); ASR path untouched.",
        "",
        "| preset | ffmpeg `-af` |",
        "|---|---|",
        "| `C0_raw` | _(none)_ |",
        "| `C1_comp_light` | acompressor thr≈−30 dBFS ratio=4 makeup×4 |",
        "| `C2_comp_hot` | acompressor ratio=6 makeup×8 + alimiter |",
        "| `C3_dynaudnorm` | dynaudnorm f=150 g=7 |",
        "",
        "## Coverage",
        "",
        "| kind | window | C0 | C1 | C2 | C3 | note |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for win in WINDOWS:
        b = by_win[win.name]
        lines.append(
            f"| {win.kind} | `{win.name}` | "
            + " | ".join(f"{b[p]['cover']:.2%}" for p in presets)
            + f" | {win.note} |"
        )

    lines.extend(["", "## Rescue Δ cover vs C0", ""])
    for win in WINDOWS:
        if win.kind != "rescue":
            continue
        b = by_win[win.name]
        c0 = b["C0_raw"]["cover"]
        parts = ", ".join(
            f"{p.replace('C0_raw', 'C0')} {b[p]['cover'] - c0:+.1%}" for p in presets[1:]
        )
        lines.append(f"- `{win.name}`: C0={c0:.1%}; {parts}")

    lines.extend(["", "## Regression Δ cover vs C0", ""])
    for win in WINDOWS:
        if win.kind != "regression":
            continue
        b = by_win[win.name]
        c0 = b["C0_raw"]["cover"]
        drops = []
        for p in presets[1:]:
            d = b[p]["cover"] - c0
            flag = " WARN" if d < -0.05 else ""
            drops.append(f"{p} {d:+.1%}{flag}")
        lines.append(f"- `{win.name}`: C0={c0:.1%}; " + ", ".join(drops))

    # Simple verdict heuristics
    rescue_gains = []
    for win in WINDOWS:
        if win.kind != "rescue":
            continue
        b = by_win[win.name]
        c0 = b["C0_raw"]["cover"]
        best = max(presets[1:], key=lambda p: b[p]["cover"])
        rescue_gains.append((win.name, best, b[best]["cover"] - c0, b[best]["cover"], c0))

    lines.extend(["", "## Verdict", ""])
    meaningful = [g for g in rescue_gains if g[2] >= 0.05 and g[3] >= 0.15]
    if meaningful:
        lines.append(
            "Compressor **helps** on at least one rescue window "
            "(Δ≥5pp and cover≥15%): "
            + ", ".join(f"`{n}` via {p} ({c0:.0%}→{c:.0%})" for n, p, _, c, c0 in meaningful)
            + "."
        )
    else:
        best_overall = max(rescue_gains, key=lambda g: g[2])
        lines.append(
            "No strong rescue recovery (no window with Δ≥5pp and cover≥15%). "
            f"Best delta: `{best_overall[0]}` {best_overall[1]} "
            f"{best_overall[4]:.1%}→{best_overall[3]:.1%} ({best_overall[2]:+.1%})."
        )
    lines.append(
        "If still weak → dual-path alone is not enough; revisit hole-fallback (FSMN/TEN)."
    )
    lines.append("")

    text = "\n".join(lines)
    (OUT / "vad_compressor.md").write_text(text, encoding="utf-8")
    report = ROOT / "agent_docs" / "reports" / "d1_vad_compressor.md"
    report.write_text(text, encoding="utf-8")
    print(f"Wrote {OUT / 'vad_compressor.md'} and {report}")


if __name__ == "__main__":
    main()

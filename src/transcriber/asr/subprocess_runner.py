"""Запуск распознавания ASR в изолированном дочернем процессе для освобождения памяти."""

import argparse
import subprocess
import sys
from pathlib import Path

from transcriber.models.artifacts import (
    TranscriptArtifact,
    TurnsArtifact,
    dump_artifact,
    load_artifact,
)


def run_asr_subprocess(
    wav_path: Path,
    turns_path: Path,
    out_path: Path,
    max_segment_sec: int = 25,
    gain_db: float = 0.0,
    per_turn_gain: bool = True,
    job_id: str | None = None,
) -> TranscriptArtifact:
    """Запускает процесс транскрибации через subprocess и читает результирующий артефакт."""
    cmd = [
        sys.executable,
        "-m",
        "transcriber.asr.subprocess_runner",
        "--wav",
        str(wav_path),
        "--turns",
        str(turns_path),
        "--out",
        str(out_path),
        "--max-segment-sec",
        str(max_segment_sec),
        "--gain-db",
        str(gain_db),
        "--per-turn-gain",
        "1" if per_turn_gain else "0",
    ]
    if job_id:
        cmd.extend(["--job-id", job_id])

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        err_msg = (
            f"ASR subprocess failed (exit code {result.returncode}):\n"
            f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
        raise RuntimeError(err_msg)

    if not out_path.is_file():
        raise FileNotFoundError(f"ASR subprocess did not produce expected artifact: {out_path}")

    return load_artifact(out_path, TranscriptArtifact)


def main() -> None:
    """Точка входа дочернего процесса ASR."""
    parser = argparse.ArgumentParser(description="ASR subprocess worker")
    parser.add_argument("--wav", type=str, required=True, help="Path to input WAV")
    parser.add_argument("--turns", type=str, required=True, help="Path to turns.json")
    parser.add_argument("--out", type=str, required=True, help="Path to output transcript.json")
    parser.add_argument(
        "--max-segment-sec", type=int, default=25, help="Max segment length in seconds"
    )
    parser.add_argument("--gain-db", type=float, default=0.0, help="Legacy whole-file gain dB")
    parser.add_argument(
        "--per-turn-gain",
        type=str,
        default="1",
        help="1/0: apply linear gain per ASR slice",
    )
    parser.add_argument("--job-id", type=str, default=None, help="Job ID")

    args = parser.parse_args()

    from transcriber.asr.gigaam import transcribe_slices_with_model

    turns = load_artifact(Path(args.turns), TurnsArtifact)
    transcript = transcribe_slices_with_model(
        wav_path=Path(args.wav),
        turns=turns,
        max_segment_sec=args.max_segment_sec,
        gain_db=args.gain_db,
        per_turn_gain=args.per_turn_gain not in {"0", "false", "False"},
        job_id=args.job_id,
    )

    dump_artifact(transcript, Path(args.out))


if __name__ == "__main__":
    main()

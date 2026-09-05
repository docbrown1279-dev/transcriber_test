"""Консольный интерфейс проверки качества стенограмм (шлюз G1)."""

import argparse
import sys
from pathlib import Path

from transcriber.models.artifacts import (
    TranscriptArtifact,
    dump_artifact,
    load_artifact,
)
from transcriber.quality.checks import build_quality_artifact


def main() -> None:
    parser = argparse.ArgumentParser(description="Transcriber Quality Gate G1 checker")
    subparsers = parser.add_subparsers(dest="command", required=True)

    check_parser = subparsers.add_parser("check-transcript", help="Check transcript quality")
    check_parser.add_argument("transcript", type=str, help="Path to transcript.json")
    check_parser.add_argument(
        "--audio-duration", type=float, default=None, help="Audio duration in seconds"
    )
    check_parser.add_argument("--out", type=str, default=None, help="Path to write quality.json")

    args = parser.parse_args()

    if args.command == "check-transcript":
        transcript_path = Path(args.transcript)
        if not transcript_path.is_file():
            print(f"Error: transcript file not found: {transcript_path}", file=sys.stderr)
            sys.exit(1)

        transcript = load_artifact(transcript_path, TranscriptArtifact)
        quality = build_quality_artifact(
            transcript=transcript,
            audio_duration_sec=args.audio_duration,
        )

        if args.out:
            out_path = Path(args.out)
            dump_artifact(quality, out_path)
            print(f"Saved quality artifact to {out_path}")

        print(f"Quality verdict: {quality.verdict.upper()}")
        print(
            f"Russian word ratio: {quality.russian_word_ratio:.3f} (words: {quality.total_words})"
        )
        print(f"Latin characters: {quality.latin_chars_in_segments}")
        print(
            f"Empty segments: {quality.empty_segments}, "
            f"Holes total: {quality.hole_sec_total:.1f} s"
        )

        for c in quality.checks:
            print(f"  [{c.status.upper()}] {c.id}: {c.message}")

        if quality.verdict == "fail":
            sys.exit(1)


if __name__ == "__main__":
    main()

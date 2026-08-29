#!/usr/bin/env python3
"""Run pyrnnoise while supporting audiolab's current metadata API."""

from __future__ import annotations

import argparse
from pathlib import Path

from audiolab import Reader, info
from pyrnnoise import RNNoise


if not hasattr(Reader, "rate"):
    Reader.rate = property(lambda self: self.sample_rate)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    metadata = info(str(args.input))
    sample_rate = getattr(metadata, "sample_rate", None)
    if sample_rate is None:
        sample_rate = metadata.rate

    args.output.parent.mkdir(parents=True, exist_ok=True)
    denoiser = RNNoise(sample_rate)
    frame_count = sum(
        probabilities.shape[1]
        for probabilities in denoiser.denoise_wav(
            str(args.input),
            str(args.output),
        )
    )
    print(f"processed_probability_frames={frame_count}")


if __name__ == "__main__":
    main()

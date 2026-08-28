#!/usr/bin/env bash
# Create noisy excerpt and denoise variants (ffmpeg-first).
set -euo pipefail
SRC="${1:-/workspace/data/processed/meeting_sample_16k.wav}"
OUT_DIR="${2:-/workspace/data/processed/denoise}"
EXCERPT_SEC="${3:-180}"
mkdir -p "$OUT_DIR" /workspace/results/denoise

ffmpeg -y -i "$SRC" -t "$EXCERPT_SEC" -ac 1 -ar 16000 "$OUT_DIR/excerpt_clean.wav" </dev/null 2>/dev/null

ffmpeg -y -f lavfi -i "anoisesrc=color=pink:sample_rate=16000:amplitude=0.05:duration=${EXCERPT_SEC}" \
  "$OUT_DIR/pink_noise.wav" </dev/null 2>/dev/null

ffmpeg -y -i "$OUT_DIR/excerpt_clean.wav" -i "$OUT_DIR/pink_noise.wav" \
  -filter_complex "[0:a][1:a]amix=inputs=2:duration=first:dropout_transition=0,volume=1.4" \
  "$OUT_DIR/excerpt_noisy.wav" </dev/null 2>/dev/null

ffmpeg -y -i "$OUT_DIR/excerpt_noisy.wav" \
  -af "highpass=f=80,afftdn=nf=-25:nt=w" \
  "$OUT_DIR/denoised_ffmpeg_afftdn.wav" </dev/null 2>/dev/null

ffmpeg -y -i "$OUT_DIR/excerpt_noisy.wav" \
  -af "highpass=f=100,anlmdn=s=0.0005:p=0.002:r=0.002" \
  "$OUT_DIR/denoised_ffmpeg_anlmdn.wav" </dev/null 2>/dev/null

ls -lh "$OUT_DIR"/*.wav
echo "DONE"

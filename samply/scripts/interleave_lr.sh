#!/usr/bin/env bash
# Interleave two mono files into one stereo WAV.
# First arg -> LEFT channel, second arg -> RIGHT channel.
# Convention for lighting: SMPTE timecode on L, program audio (FOH/click) on R.
#
# Usage: interleave_lr.sh LEFT.flac RIGHT.flac OUTPUT.wav [pcm_s24le|pcm_s16le]
set -euo pipefail

LEFT="${1:?need LEFT (timecode) file}"
RIGHT="${2:?need RIGHT (audio) file}"
OUT="${3:?need OUTPUT .wav path}"
CODEC="${4:-pcm_s24le}"   # 24-bit default; use pcm_s16le for 16-bit sources

ffmpeg -y \
  -i "$LEFT" \
  -i "$RIGHT" \
  -filter_complex "[0:a][1:a]join=inputs=2:channel_layout=stereo[a]" \
  -map "[a]" \
  -c:a "$CODEC" \
  "$OUT"

echo "wrote $OUT  (L=$LEFT  R=$RIGHT  codec=$CODEC)"

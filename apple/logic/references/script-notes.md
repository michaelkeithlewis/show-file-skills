# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/locate_clip.py

- locate_clip.py <source.wav> <clip.wav> Find where a short clip sits inside a long source recording (FFT cross-correlation, coarse at 2 kHz then sample-accurate at 48 kHz) and report the gain between them. Use it to line up a re-bounce against a file you already have. Needs ffmpeg and numpy.
- normalise by local energy of ref

## scripts/logic_pd.py

- strip with a live input (observed) strip whose input is a bus (observed)
- AUSampleDelay ClassInfo: 'data' = 16 zero bytes + big-endian float32 delay in samples
- 'appl' 'aufx' 'sdly', each reversed

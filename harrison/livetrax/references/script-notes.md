# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/lt_template.py

- direct outs = virtual soundcheck playback
- mono tracks keep the default panner, stereo tracks get balance
- Master: inputs from tracks flagged master=1 (Connection lives on both ends), outputs per --master-out
- GUI state is keyed by old route ids; drop it and let LiveTrax rebuild defaults

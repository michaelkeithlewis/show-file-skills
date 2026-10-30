# Script notes

Facts that used to sit in code comments, by script. The scripts in this repo carry no comments.

## scripts/lp_generate.py

- channelId >= 4096 = MIDI ports on a node
- hardware: device, channel count, labels
- song snapshots go; the top-level GlobalSnapshot stays as the current state
- current-state copy of chains and plugins, derived from the Chains list (see check_derive.py)
- audio patch: HW IN n -> chain -> HW OUT n
- plugin windows of removed plugins go
- wire view: hardware left and right, chains in columns of 14
- nothing may still point at a removed chain or plugin

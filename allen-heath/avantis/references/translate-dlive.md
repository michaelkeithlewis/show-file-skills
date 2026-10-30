# Converting between Avantis and dLive

What carries over, what changes, what gets lost. Both directions were run on real shows and loaded on an
Avantis Solo (FW 2.01) and a dLive S3000 (FW 2.12).

## Approach

Start from an empty show of the target console (a template saved from Director), set its bus config, then
copy the source sections into it. Never patch a source show into the other format in place.

- dLive to Avantis: write Bridge-4 (loads on FW 1.x and 2.x). Only the live state (scene 65535) is
  translated; stored scenes are not.
- Avantis to dLive: regrow the dLive template to the target bus config the way Director does it
  (`allen-heath/dlive/scripts/dlive_mix.py`), then fill it.

## What carries over

- Names and colours, stereo pairs, bus config (within the target budget, see `mixer.md`).
- Input mix: faders, mutes, pans, sends, group and DCA assigns, main assign.
- Bus masters, bus to bus sends, FX return levels, DCA levels.
- Strip assign (bank by bank, cut to the target surface).
- Input patch (default mapping below) and preamp gain, pad and 48V onto the target socket where the socket
  family exists on both sides (dLive MixRack, Avantis local and SLink).
- Trim and polarity.
- Input processing: preamp model, HPF, LPF, PEQ, gate, compressor (with model), delay, stereo image,
  direct out. Bus processing: PEQ, GEQ (all 28 bands), compressor, delay. FX return EQ.
- FX rack with all parameters (type ID translated, table below). dLive AHFX to Avantis Ultra FX and back,
  when the target has the Ultra FX card.

## What changes

- Channels: dLive has 128 inputs, Avantis 64 (96 with dPack). Pick which inputs to keep; processing and sends
  follow the channel to its new number.
- DCAs: 24 on dLive, 16 on Avantis.
- Group to group: dLive only. Resolve it when going to Avantis: every input (and FX return) of the source
  group is also assigned straight to the target group, following chains transitively.
- Buses: dropping a bus renumbers the rest of its type. Names, sends, mix rows, bus to bus sends, bus
  processing, side chain sources and strip assign all have to follow the new numbers. Keep mono counts even.
- Strip and side chain type codes shift by one from mono matrix on (`patch-and-io.md`).
- CompStortion (model 10) only on Avantis FW 2.x; to Bridge-4 it becomes Manual RMS.
- HPF slopes 18 dB Bessel and 6 dB do not exist on Avantis; they become 12 dB.

## Default patch mapping

| From | To |
|---|---|
| dLive MixRack, I/O Port 1-5, DX1, DX3, surface DX | Avantis SLink, same number (check the rig) |
| dLive surface analogue | Avantis local |
| AES, USB | AES, USB |
| Avantis SLink | dLive I/O Port 1 |
| Avantis I/O Port 1, 2 | dLive I/O Port 1, 2 (on a CDM rack: I/O Port 4 of the surface) |
| Avantis local | dLive surface analogue |

## What gets lost

- Stored scenes in the dLive to Avantis direction.
- UFX send levels on the channels and the UFX return mix (Bridge-5 row format not verified yet).
- Output patch.
- Preamps on families that only one side has (dLive DX, surface and I/O port boxes).
- Bus compressor bytes without a counterpart (`processing.md`).
- Bridge-4 coefficients come out 1 or 2 LSB different from the console's own after a round trip
  (fitted model, inaudible).

## FX type IDs

| Effect | dLive | Avantis |
|---|---|---|
| SMR Reverb | 2 | 2 |
| SMR Room | 3 | 5 |
| EMT 250 | 4 | 4 |
| Chorus | 8 | 7 |
| ADT | 9 | 8 |
| Gated Echo / Echo | 14 | 0x17 (unconfirmed) |
| DeEsser | 21 | 0x0d |
| Transient Controller | 31 | 0x14 |
| Stereo Tap Delay | 35 | 0x16 |
| Bass Fix, IEM Glue, Guitar Cntrl, BBD Delay | 28, 29, 30, 34 | none |

Ultra FX / AHFX types (same on both): 0x1c Vox Studio, 0x1d Plate, 0x1e Tuner, 0x23 Dual Harmony,
0x24 Shifter, 0x28 Gridder, 0x2a AmpCab, 0x2b Saturator, 0x2d Ping Pong Delay.

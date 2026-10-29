# DiGiCo SD/Quantum input channel: architecture (from V1528 manual, applies to Q2 v2242)

Source: SD & Quantum Software Reference Manual. This is the "what's possible" map and the
blueprint for the canonical IR. [done] = decoded with a writer, [todo] = not yet mapped, [partial] = located, not fully mapped.
Offsets are the early fixed offsets of one 48-channel Q225 default; use the keys in `FORMAT.md` for writing.

## Signal flow (input channel)
Input/Trim -> Channel Delay -> DiGiTube -> Filters(HPF/LPF) -> [Insert A] -> EQ <-> Dynamics -> [Insert B] -> Mute -> Fader
- **EQ<->Dyn order is a per-channel switch** (default eq-dyn, reversible to dyn-eq). [done] (04, 81, 0), see Input / Trim.
- **Mustard** (Quantum) runs alongside, insertable at 1 of **5 positions**. [todo]

## Input / Trim  [done](trim,polarity) [todo](phantom,gaintrack,alt)
- [done] trim @0x13f45 (dB), polarity @0x13f5d (1.0=inv). phantom/gain-track/alt [todo]
- [done] EQ<->Dyn order @0x141cd (1.0=dyn->eq).

## Channel Delay  [done](amount)
- [done] delay @0x1401f (SECONDS; 50ms->0.04998 quantized). on/units [todo]

## DiGiTube (channel valve emulation, distinct from Mustard tube)  [done]
- [done] on @0x13fad, drive @0x13fb5 (default 1.0), bias @0x13fbd (default 3.0). warmth [todo]

## Filters  [done](in/freq) [todo](slope option)
- HPF + LPF, **24 dB/oct**, freq each. (Some consoles can swap to 4x24dB filters vs parametric.)
- [done] LPF in @0x14081, LPF freq @0x14089, HPF in @0x14091, HPF freq @0x14099.

## EQ: 4 bands  [done](core) [todo](dynamic params, order)
- per band: gain **±18 dB**, freq **20Hz–20kHz**, Q; shape **bell / hi-or-lo shelf**; **precision/classic**.
- eq on. [done] all of this (in @0x141c5; band freq @0x14305-(N-1)*0x60; shape@-8 bell1/loshelf3/hishelf4;
  freq+0; Q+8; gain+0x10; prec/classic+0x20; dyneq-enable+0x28).
- **Dynamic EQ** per band (rel band freq) [done] FULL: enable+0x28, threshold+0x30, attack+0x38(s), release+0x40(s), ratio+0x48, over/under+0x50 (over=0/under=1).

## Dynamics: 2 modules (order switchable)
### Dyn1 = Compressor | Multiband | De-esser   [done](mode, comp, multiband) [partial](de-esser)
- mode @0x143a7 (comp=0, multi=1, deesser=2). [done]
- **Compressor**: threshold, attack, release, ratio, gain(makeup), **auto gain**, **knee hard/mid/soft**. [done]
  (in@0x143af, thr@0x143bf[x3 mirror], knee@0x143c7 hard0/med1/soft2, atk@0x143cf[s], rel@0x143d7[s],
   ratio@0x143df, makeup@0x143e7, autogain@0x143ef)
- **Multiband**: 3 bands, each = full comp param set + on; 2 crossover freqs (20Hz–20kHz); all-on; listen. [done]
  Band byte per band: **lo = 0, mid = 2, hi = 1** (console-confirmed: the console's multiband screen, and a session
  written by bytes showed each value on the right band on a Quantum 112). Per band (module 05, band b): on 03,
  threshold 0e, attack 11 (s), release 12 (s), ratio 10, gain 09. Crossovers: lo (05, 05, 0) default 130 Hz, hi
  (05, 05, 1) default 1 kHz. Keys `mb1_*` / `mb2_*` / `mb3_*` = lo / mid / hi.
- **De-esser**: comp-like + bandpass sidechain (centre freq + width), listen, **no makeup**. [partial]
  Threshold, attack, release and ratio use the compressor's keys (band 0); the side-chain band is not mapped.

### Dyn2 = Gate | Ducker | Compressor   [done](mode, gate, comp, key, key filter)
- mode @0x14497 (gate=0, duck=1, comp=2). [done]
- **Gate**: threshold, attack, hold, release, range; **key** [done]: key input (05, 16, 0) = the source as a route
  `00 00 <index> <type>` (a channel 01, or an input socket 1c + k; 0 = none), key on (05, 37, 0). Console sample: keying
  input 3's gate from input 4 wrote `00 00 03 01` and 1.0, nothing else. Key filter [done]: high-pass (05, 05, 3), low-pass
  (05, 05, 2). ripple/key-listen [todo]. The 0x14491 noted here before sits inside (05, 14, 0), the dynamics' stereo
  link (each half of a stereo bus names the other there; `buses.py` KEY_ROUTE). [done]params+key
  (in@0x1449f, thr@0x144a7, atk@0x144af[s], rel@0x144b7[s], hold@0x144bf[s], range@0x144c7[dB +ve])
- **Ducker**: same controls as gate (opposite action). [done]params(shared)
- **Compressor**: = Dyn1 single-band comp + sidechain bandpass + S/C external input. [done]: ratio (05, 10, 3),
  gain (05, 09, 3), threshold / attack / release as the gate; key and key filter as the gate.

## Inserts A & B  [done](A on/pos, B on) [todo](B pos, routing)
- [done] Insert A on @0x140eb, Insert B on @0x14133, Insert A position @0x1411d (u16):
  pre-EQ/dyn=0x4080(default), pre-processing=0x40a0, post-fade=0x0000. mid-EQ/dyn & post-processing
  are N/A for Insert A (occupied: matches manual's "2 unavailable"). Insert B position offset [todo], insert routing [todo].

## Mustard (Quantum only): parallel processing, 5 insert positions  [partial] LOCATED, sections need focused captures
- Mustard lives in the TAIL of each channel's 0x12f6 block (after fader/mute), ch1-equiv offsets:
  Tube ~0x14e4e-0x14e60 (drive @0x14e5f), M-EQ ~0x14f62-0x14feb (b1 gain @0x14feb),
  M-Comp ~0x1503d-0x15048 (ch8 LevelingAmp->8.0 @0x1503d), M-Gate ~0x15157-0x15187 (ducker->2.0 @0x15157).
- Common noise offsets in this region (ignore): 0x14de0,0x14e2a,0x14edc,0x14f46,0x15020,0x1513a.
- NEEDS per-section captures w/ distinct values (tube[done], EQ, 4 comp models, gate) to fully map. Below = manual spec:
- [done] TUBE mapped: type@0x14e47(simple=1/amp=0), on@0x14e4f, preset@0x14e57(oddharm0/evenharm1/overdrive2/
  distortion3/crunch4/highdist5), drive@0x14e5f(0-1,def0.5), output@0x14e97(dB,def-6),
  amp: drive@0x14e67, bias@0x14e77(def11), saturate@0x14e87. (amp per-stage harmonics/HF-boost still TODO)
- [done] M-EQ mapped: on@0x14f63; 4 bands stride 0x20 (b4->b1 asc), b1 freq@0x14fdb, bandN=0x14fdb-(N-1)*0x20;
  per band shape@-0x08 (bell1/loshelf3/hishelf4/allpass9), freq+0, Q+8, gain+0x10. M-EQ HPF/LPF still TODO (ch4 cap didn't land).
- **Tube/Preamp**: type = simple Tube (drive, output gain, 6 presets: odd/even harm, overdrive,
  distortion, crunch, high dist) OR advanced **Amp model** (2-stage, per-stage odd/even harmonics,
  drive, bias[mid=11]+saturate, HF boost >6kHz shelf, output gain).
- **EQ**: 4 parametric bands (top/bottom->shelf, mid two->all-pass) + HPF/LPF 24dB/8ve.
- **Compressor**: 4 models: Classic (thr/atk/rel/ratio, hard/soft knee, RMS/peak),
  Vintage VCA (fixed atk, auto rel, thr+ratio), Optical (3 atk/rec options, ratio),
  FET Limiter (fixed thr, in/out gain, atk/rel, ratio 4/8/12/20:1); all: on, wet/dry mix, output gain,
  sidechain HPF/LPF + s/c listen, external sidechain (shared w/ gate).
- **Gate/Ducker**: like SD gate/ducker, different atk/rel shapes; external sidechain shareable.

## Name  [done](≤8) [todo](long/variable)
- short name length-prefixed slot (≤8 chars, ~20 copies). Long names overflow to a variable region. [todo]

## Other channel types (for IR completeness)  [todo]
- Aux/Group/Matrix outputs: input/trim differs; output EQ may be 4-band+HPF/LPF or **8-band** (pre/post-insert).
- Routing/patching, bus sends (6 positions), bus assignments. [todo]

Later findings (stereo inputs, Mustard comp keys, Spice Rack, SD FX, dynamic EQ, levels): `FORMAT.md`.

# DiGiCo SD/Quantum input channel: architecture (from V1528 manual, applies to Q2 v2242)

Source: SD & Quantum Software Reference Manual. This is the "what's possible" map and the
blueprint for the canonical IR. [done] = decoded with a writer, [todo] = not yet mapped, [partial] = located, not fully mapped.
Offsets are the early fixed offsets of one 48-channel Q225 default; use the keys in `FORMAT.md` for writing.

## Signal flow (input channel)
Input/Trim -> Channel Delay -> DiGiTube -> Filters(HPF/LPF) -> [Insert A] -> EQ <-> Dynamics -> [Insert B] -> Mute -> Fader
- **EQ<->Dyn order is a per-channel switch** (default eq-dyn, reversible to dyn-eq). [done] (04, 81, 0), see Input / Trim.
- **Mustard** (Quantum) runs alongside, insertable at 1 of **5 positions**. [done] (1a, e1, 0), the codes of the inserts below.

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
### Dyn1 = Compressor | Multiband | De-esser   [done]mode/comp [todo](multiband, deesser)
- mode @0x143a7 (comp=0, multi=1, deesser=2). [done]
- **Compressor**: threshold, attack, release, ratio, gain(makeup), **auto gain**, **knee hard/mid/soft**. [done]
  (in@0x143af, thr@0x143bf[x3 mirror], knee@0x143c7 hard0/med1/soft2, atk@0x143cf[s], rel@0x143d7[s],
   ratio@0x143df, makeup@0x143e7, autogain@0x143ef)
- **Multiband**: 3 bands, each = full comp param set + on; 2 crossover freqs (20Hz–20kHz); all-on; listen. [todo]
- **De-esser**: comp-like + bandpass sidechain (centre freq + width), listen, **no makeup**. [todo]

### Dyn2 = Gate | Ducker | Compressor   [done]mode/gate [todo](sidechain, key)
- mode @0x14497 (gate=0, duck=1, comp=2). [done]
- **Gate**: threshold, attack, hold, release, range; **key route** [done] @0x14491 (u16: 0=off,
  else 0x0100|(target_ch-1)); ripple/key-listen [todo]; bandpass sidechain (freq+width) [todo]. [done]params+key
  (in@0x1449f, thr@0x144a7, atk@0x144af[s], rel@0x144b7[s], hold@0x144bf[s], range@0x144c7[dB +ve])
- **Ducker**: same controls as gate (opposite action). [done]params(shared)
- **Compressor**: = Dyn1 single-band comp + sidechain bandpass + S/C external input. [todo](sidechain)

## Inserts A & B  [done](on, position, routing)
- [done] Insert A on @0x140eb, Insert B on @0x14133, Insert A position @0x1411d (u16):
  pre-EQ/dyn=0x4080(default), pre-processing=0x40a0, post-fade=0x0000. mid-EQ/dyn & post-processing
  are N/A for Insert A (occupied: matches manual's "2 unavailable").
- [done] Positions are floats (the u16s above are their high halves): (08, e1, 0) insert A, (08, e1, 1) insert B,
  (1a, e1, 0) Mustard. 5.0 pre-processing (after the filters), 4.0 pre-EQ/dyn, 3.0 mid-EQ/dyn, 2.0 pre-fader,
  0.0 post-fader. Inserts A, B and Mustard each take a different position; the console refuses a second item in one.
- [done] Routing (console samples, Quantum 112): the send is the output socket's (12, 00, 0) route with tap `08 00`
  (insert A) or `08 10` (insert B) as its first two bytes, plus the channel's (08, fe, 0 / 1) pointing at that socket;
  the return is (08, 00, 0 / 1) = the input socket's route `00 00 <index> <type>`. FX units and Spice Rack slots on an
  insert use the same two slots, pointing at the unit (`00 00 k 0e`, `00 00 k 18`).

## Mustard (Quantum only): parallel processing, 5 insert positions  [done](position, tube, amp, filters, EQ, comp models, gate/MSE)
- Mustard lives in the TAIL of each channel's 0x12f6 block (after fader/mute), ch1-equiv offsets:
  Tube ~0x14e4e-0x14e60 (drive @0x14e5f), M-EQ ~0x14f62-0x14feb (b1 gain @0x14feb),
  M-Comp ~0x1503d-0x15048 (ch8 LevelingAmp->8.0 @0x1503d), M-Gate ~0x15157-0x15187 (ducker->2.0 @0x15157).
- Common noise offsets in this region (ignore): 0x14de0,0x14e2a,0x14edc,0x14f46,0x15020,0x1513a.
- Keys for every section: "Keys" below (written by bytes and shown right on a Quantum 112 unless marked). Manual spec
  after it:
- [done] TUBE mapped: type@0x14e47(simple=1/amp=0), on@0x14e4f, preset@0x14e57(oddharm0/evenharm1/overdrive2/
  distortion3/crunch4/highdist5), drive@0x14e5f(0-1,def0.5), output@0x14e97(dB,def-6),
  amp: drive@0x14e67, bias@0x14e77(def11), saturate@0x14e87. [done] amp drive type (1a, 37, 0) 0 even / 1 odd
  harmonics, bias type (1a, 39, 0) 0 off / 1 even / 2 odd, HF boost (1a, 05, 0) dB.
- [done] M-EQ mapped: on@0x14f63; 4 bands stride 0x20 (b4->b1 asc), b1 freq@0x14fdb, bandN=0x14fdb-(N-1)*0x20;
  per band shape@-0x08 (bell1/loshelf3/hishelf4/allpass9), freq+0, Q+8, gain+0x10. [done] M-EQ HPF/LPF are module 1b:
  HPF on / freq (1b, 03, 1) / (1b, 05, 1), LPF (1b, 03, 0) / (1b, 05, 0), as the channel filters (the x 1.25 / x 0.8
  display factor assumed, not checked).
- **Tube/Preamp**: type = simple Tube (drive, output gain, 6 presets: odd/even harm, overdrive,
  distortion, crunch, high dist) OR advanced **Amp model** (2-stage, per-stage odd/even harmonics,
  drive, bias[mid=11]+saturate, HF boost >6kHz shelf, output gain).
- **EQ**: 4 parametric bands (top/bottom->shelf, mid two->all-pass) + HPF/LPF 24dB/8ve.
- **Compressor**: 4 models: Classic (thr/atk/rel/ratio, hard/soft knee, RMS/peak),
  Vintage VCA (fixed atk, auto rel, thr+ratio), Optical (3 atk/rec options, ratio),
  FET Limiter (fixed thr, in/out gain, atk/rel, ratio 4/8/12/20:1); all: on, wet/dry mix, output gain,
  sidechain HPF/LPF + s/c listen, external sidechain (shared w/ gate).
- **Gate/Ducker**: like SD gate/ducker, different atk/rel shapes; external sidechain shareable.
- **Keys** (band 0 throughout):
  - Pre-amp 1a: type 3b (1 tube, 0 amp), on 02, position e1 (default 3.0). Tube: mode 45, drive 1b (0-1), output 3c.
    Amp: drive 38 (dB), drive type 37, bias 1a, bias type 39, saturate 3a (a button), HF boost 05, output 3c.
  - Comp 1d: model 0b (0 Classic, 3 Vintage VCA, 4 FET, 5 Optical, 8 Leveling amp), on 02, mix 47 (1.0 = 100 %),
    threshold 0e, knee 0f (1 hard, 0 soft), attack 11 / release 12 (s), ratio 10, gain 09, sensing 46 (0 RMS,
    1 peak), side-chain filter on 03 with low (05, 1) and high (05, 0), stereo link 3f.
    Optical: attack 48 and recovery 49 (0 fast, 1 medium, 2 slow); the ratio is a step, 4c: 2, 3, 4, 5 with the ratio
    10 at 2:1, 3:1, 4:1, 6:1 in real sessions. FET: input 41, ratio button 4a (1 4:1, 2 8:1, 3 12:1, 4 20:1), output 4d.
    Leveling amp: mode 50 (0 compress, 1 limit), gain 51 (default 25), peak reduction 52 (default 20), side-chain
    emphasis 53 (51-53 not console-tested).
    Controls per model: Classic threshold, attack, release, ratio, gain, mix, knee, sensing; Vintage VCA threshold,
    ratio, gain, mix; FET input, attack, release, output, ratio buttons, mix; Optical threshold, ratio step, gain, mix,
    attack, recovery; Leveling amp peak reduction, gain, mix, compress / limit.
  - Gate 1e: mode 0b (0 gate, 1 ducker, 2 **MSE**, Mustard Source Expander), on 02, threshold 0e, range 0a (positive
    dB), attack 11, hold 13, release 12, MSE release button 4c, side-chain filter on 03 / low (05, 1) / high (05, 0),
    key input 16 and key on 37 as the SD gate. MSE shows threshold, depth (range) and the release button.

## Name  [done](≤8) [todo](long/variable)
- short name length-prefixed slot (≤8 chars, ~20 copies). Long names overflow to a variable region. [todo]

## Other channel types (for IR completeness)  [todo]
- Aux/Group/Matrix outputs: input/trim differs; output EQ may be 4-band+HPF/LPF or **8-band** (pre/post-insert).
- Routing/patching, bus sends (6 positions), bus assignments. [todo]

Later findings (stereo inputs, Mustard comp keys, Spice Rack, SD FX, dynamic EQ, levels): `FORMAT.md`.

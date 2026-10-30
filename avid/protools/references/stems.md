# Stems and instrumentals (solo-in-place)

Print stems **solo-in-place** so every stem gets all the processing: solo one folder,
everything else is implicitly muted, and the solo-safe returns keep running. Mark the
master bus, any glue reverb or parallel buses, drum triggers and every FX return as
solo safe in your template. A stem then carries its own reverbs, its bus chain and the
master chain. Bounce the **PtMst** bus.

Print stems only after the client approves the final mixes. A stem set must match the
final master exactly.

## Delivery format

```
Bounced Files/<Song> FINALS/
    <Song>_<Initials>_V<n>_PtMst.wav              the approved final (and _PrMst.wav for mastering)
    <Song>_<Initials>_V<n>_Instrumental_PtMst.wav
    <Song> STEMS/<Song>_<STEM>.wav
    <Song> STEMS.zip                              ditto -c -k --sequesterRsrc --keepParent
```

- STEM names are caps, one word or short: DRUMS (or KICK, SNR, TOMS), BASS / BASS DI /
  BASS SYNTH, AGs or AG1-3, EGs or EG1-7 / EG LD / EG RHYTHM, KEYS / PIANO / B3 /
  SYNTHS, ORCH / VIOLIN, PERC / PERC FX / TAMBO, FX, LVs, BGVs, CLICK, GUIDE.
- Interleaved stereo WAV, 16-bit, at the session's native sample rate. A 96 kHz
  session bounces at 48 kHz. `--bits 24` or `--rate N` override this when a client
  asks.

## Steps

1. Open the session that made the approved final. Use the final's exact range (the
   same selection, memory location or sample in/out), so every stem lines up with it
   sample for sample. If the delivered final was trimmed after the bounce, add the
   trim to `--in`.
2. Pick the stems from the song's material.
   - When the producer's multitracks came in category folders (`DRUMS/`, `STRINGS/`,
     `VOX/` ...), run `scripts/stems.py plan --map producer`. Each track joins the
     stem named after the folder its source file came from. Tracks built in the
     session (comps, merged pairs, mono conversions) match by name. VOX splits into
     LVs and BGVs. Guitars split into AGs (names with ACOUSTIC) and EGs. A stem that
     is silent over the range is dropped.
   - Otherwise run `scripts/stems.py plan`. Every top-level folder, and every folder
     directly inside BAND or VOCALS, becomes one stem. Sub-folders ride with their
     parent.
   - For finer stems (EG1, EG2, KICK, SNR), write a `map.json`
     `{stem: [tracks or folders to solo]}`.
3. Run `scripts/stems.py bounce --song "<Song>" --in <S> --out <S> --version V<n>
   --mode both --final "<final PtMst.wav>" --zip`. Use `--mode instrumental` for an
   instrumental only. Add `--click` to also print the click. The script records the
   solo states, solos each stem in turn, bounces PtMst, moves each file into the
   FINALS layout, restores the solos, and reports the peak and RMS of every file.
4. Check the sum. The summed stems never null against the final, because the master
   chain runs on each stem on its own. Check that the correlation is high. A session
   with free-running modulation (motion or tape-wow plug-ins, modulated reverbs)
   prints differently on every bounce: bounce the same range twice, and if those two
   prints do not match each other, a loose stem sum is expected.
5. Check the instrumental for vocal leaks. The VOCALS folder is excluded, so its
   returns get no signal. A vocal track with a pre-fader send to a solo-safe aux
   outside VOCALS still leaks. Listen to the vocal sections, or correlate against a
   printed LVs stem.
6. Scan for clicks. A soloed stem exposes clicks the full mix hides: plug-in
   modulation snaps, and hard edits on clip boundaries (often exactly on a bar line).
   Run `scripts/snapscan.py "<FINALS>/<Song> STEMS/"*.wav "<FINALS>/"*Instrumental*.wav`.
   Skip drum and percussion stems, whose real attacks look the same.
   - A hit with a sample step of 40x or more is a true discontinuity. Repair it with
     `scripts/declick.py F F <t> --exact`.
   - Repair the same sample in the instrumental when its step there is over 8x.
   - Leave hits under 40x alone. These are usually pick, strum or consonant attacks.
   - Re-zip any song you repaired.
7. Deliver the stems in their own folder (`Stems` or `Instrumentals`), separate from
   the folder the client reviews mixes in. For a large set, use cloud storage with a
   share link.

## Album flow: songs that run into each other

Some records cut one song straight into the next. The client's reference often shows
the cut point.

1. Bounce the first song so it ends on the cut sample, with no tail.
2. Trim the next song's leading silence. A file edit is fine, because the audio stays
   identical.
3. Keep them as two separate tracks.
4. To let the client hear the flow, make a gapless Samply Player of the two stacks
   with `../../samply/scripts/player.js`, and check it with
   `../../samply/scripts/player_check.js` (see the samply skill).

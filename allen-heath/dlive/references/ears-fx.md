# Ear mixes from the FOH desk (a tested habit, decoded from a real touring show)

- Every vocal mic has its own stereo reverb in the standard FX rack, fed straight from the IEM double-patch
  channel's direct out (FX rack input 2k-1/2k = "Ip n DO"), no aux/FX bus used. The lead vocal also gets a slap
  (for example FX 7 Hall + FX 8 Delay on the lead, one Hall per other singer, one on the acoustic).
  Global direct-out tap = Post Delay.
- Returns (FX return strip = unit): main off, no groups, fader -inf, pre-fader sends into every ear mix; the
  lead's verb sits around -6..-20, other singers' verbs -17..-35, the drummer gets little or none.
- More-me: the singer's own vocal +1..+5 in their mix, the drummer's kick up to +6.
- Starting point: a short room around 1.5 s decay and 20 ms pre-delay (plate for bigger), patch the input
  straight to the FX rack, check the pack's stereo panning. Give the band a flat version of their own sound:
  double patch and use tap points.
- In a `dlive_mix.py` plan, FX rack unit k = `FX Rtn 2k-1/2k`.

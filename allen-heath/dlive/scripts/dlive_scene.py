"""dLive StageBox scene reader/writer (firmware 2.x).
Field map from jaylenjinx/dlive-show-editor (docs/input-mixer.md, KNOWN_FORMAT.md):
- Name/colour managers: u16be len, label\0, 00 01, N x 9-byte names, N x 1-byte colours
- Input Mixer: label\0, 12-byte header [ver, monoGrp, stGrp, monoFX, stFX, monoAux, stAux, monoMtx, stMtx, mainType, mainStrips, PAFL]
  then 128 blocks: group assigns, sends (mono 4B / stereo 5B, order monoFX, monoAux, stFX, stAux, monoMtx, stMtx),
  47-byte channel section (+0 main on, +3..4 fader, +5 pan, +15..38 DCA1-24, +39..46 MG1-8), then 8x5B UFX if ver>=3
"""
import struct

class Scene:
    def __init__(self, data):
        self.d = bytearray(data)

    MANAGERS = ["Input Channel", "Mono Group Channel", "Stereo Group Channel", "Mono Aux Channel", "Stereo Aux Channel",
                "Mono FX Send Channel", "Stereo FX Send Channel", "Stereo AHFX Send Channel", "Main Channel",
                "Mono Matrix Channel", "Stereo Matrix Channel", "FX Return Channel", "AHFX Return Channel", "DCA Channel"]

    def manager(self, kind):
        sig = (kind + " Name Colour Manager").encode()
        i = 0
        while True:
            i = self.d.find(sig + b"\x00\x01", i)
            if i < 0: raise KeyError(kind)
            plen = struct.unpack(">H", self.d[i - 2:i])[0]
            body = plen - len(sig) - 2
            if body > 0 and body % 10 == 0:
                return i + len(sig) + 2, body // 10
            i += 1

    def names(self, kind):
        base, n = self.manager(kind)
        out = []
        for k in range(n):
            raw = bytes(self.d[base + 9 * k: base + 9 * k + 9])
            out.append((raw.split(b"\x00")[0].decode("latin1"), self.d[base + 9 * n + k]))
        return out

    def set_name(self, kind, idx, name=None, colour=None):
        base, n = self.manager(kind)
        assert 1 <= idx <= n
        if name is not None:
            b = name.encode("ascii")
            assert len(b) <= 8 and all(32 <= c < 127 for c in b), name
            self.d[base + 9 * (idx - 1): base + 9 * idx] = b + b"\x00" * (9 - len(b))
        if colour is not None:
            assert 0 <= colour <= 7
            self.d[base + 9 * n + idx - 1] = colour

    def mixer(self):
        i = self.d.find(b"Input Mixer\x00")
        plen = struct.unpack(">H", self.d[i - 2:i])[0]
        h = list(self.d[i + 12:i + 24])
        ver, mg, sg, mfx, sfx, maux, saux, mmtx, smtx = h[:9]
        groups = mg + sg
        sends_m = mfx + maux + mmtx
        sends_s = sfx + saux + smtx
        bs = groups + 4 * sends_m + 5 * sends_s + 47 + (40 if ver >= 3 else 0)
        state = plen - 12
        assert state - 12 == 128 * bs, (state, bs)
        first = i + 24
        sec = groups + 4 * sends_m + 5 * sends_s
        return dict(header=h, mono_groups=mg, st_groups=sg, mono_aux=maux, st_aux=saux, first=first, bs=bs, sec=sec,
                    mono_fx=mfx, st_fx=sfx, mono_mtx=mmtx, st_mtx=smtx)

    def block(self, ch):
        m = self.mixer()
        return m["first"] + (ch - 1) * m["bs"], m

    def input_state(self, ch):
        b, m = self.block(ch)
        g = list(self.d[b:b + m["mono_groups"] + m["st_groups"]])
        s = b + m["sec"]
        return dict(mono_groups=[k + 1 for k in range(m["mono_groups"]) if g[k]],
                    st_groups=[k + 1 for k in range(m["st_groups"]) if g[m["mono_groups"] + k]],
                    main=self.d[s], fader=struct.unpack(">h", self.d[s + 3:s + 5])[0],
                    dca=[k + 1 for k in range(24) if self.d[s + 15 + k]],
                    mute_groups=[k + 1 for k in range(8) if self.d[s + 39 + k]])

    def set_input(self, ch, mono_groups=None, st_groups=None, main=None, dca=None, mute_groups=None, fader_db=None):
        b, m = self.block(ch)
        s = b + m["sec"]
        if mono_groups is not None:
            for k in range(m["mono_groups"]): self.d[b + k] = 1 if (k + 1) in mono_groups else 0
        if st_groups is not None:
            for k in range(m["st_groups"]): self.d[b + m["mono_groups"] + k] = 1 if (k + 1) in st_groups else 0
        if main is not None: self.d[s] = 1 if main else 0
        if dca is not None:
            for k in range(24): self.d[s + 15 + k] = 1 if (k + 1) in dca else 0
        if mute_groups is not None:
            for k in range(8): self.d[s + 39 + k] = 1 if (k + 1) in mute_groups else 0
        if fader_db is not None:
            raw = -32767 if fader_db is None or fader_db <= -90 else int(round(fader_db * 256))
            self.d[s + 3:s + 5] = struct.pack(">h", raw)

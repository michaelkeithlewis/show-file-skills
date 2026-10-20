"""dLive scene safes / recall filter (Show/SceneSafes/*.dat and each scene header): remap to a new mixer config.
Logic = cStageBoxSceneSafesOrRecallFilter::FitFilterToMixerConfig (@0x1005a60e0); file field order =
operator<<(QIODevice&, cStageBoxSceneSafesOrRecallFilter const&) (@0x100598410).
File: 3 bytes + 13-byte mixer config, then inputs, mixes, FX, FX sends, FX returns, DCA, other, UFX, UFX sends, UFX returns."""
HDR = 16
IN0, IN_N, IN_SZ = HDR, 128, 521
MIX0, MIX_N, MIX_SZ = IN0 + IN_N * IN_SZ, 64, 518
FX0 = MIX0 + MIX_N * MIX_SZ
FXS0, FXS_N, FXS_SZ = FX0 + 32, 16, 37
FXR0, FXR_N, RET_SZ = FXS0 + FXS_N * FXS_SZ, 32, 510
UFXR_N = 8
BODY = 122077
TOTAL = HDR + BODY
UFXR0 = TOTAL - 1 - UFXR_N * RET_SZ
# record-relative offsets of the per-bus safes in FILE order
GRP = (3, 1)        # inputs/returns: 64 bytes, one per bus (group assign)
AUXT = (67, 3)      # 64 triplets (aux / FX send items)
MTXT = (259, 3)     # 64 triplets (matrix send items)
M_AUXT = (3, 3)     # mix records: 64 triplets (group -> aux/FX sends)
M_MTXT = (195, 3)   # 64 triplets (sends to matrix)
M_ARR6 = (387, 1)   # 64 bytes

def buses(c):
    out = []
    def add(t, n, st):
        for k in range(n):
            out.append((t, k))
            if st: out.append(None)
    add("MG", c["MG"], 0); add("SG", c["SG"], 1); add("mFX", c["mFX"], 0); add("mAux", c["mAux"], 0)
    add("sFX", c["sFX"], 1); add("sAux", c["sAux"], 1); add("Main", c.get("Main", 1), 1); add("PAFL", 1, 1)
    add("mMtx", c["mMtx"], 0); add("sMtx", c["sMtx"], 1)
    return (out + [None] * 64)[:64]

GROUPISH = {"MG", "SG"}; SENDISH = {"mFX", "sFX", "mAux", "sAux"}; MTXISH = {"mMtx", "sMtx"}

def fit(data, old, new, new_cfg_bytes=None):
    assert len(data) == TOTAL, len(data)
    src = bytes(data); d = bytearray(data)
    ob, nb = buses(old), buses(new)
    newbus = {k: i for i, k in enumerate(nb) if k}
    bmap = [(b, newbus.get(k), k) for b, k in enumerate(ob) if k and k[0] != "PAFL" and newbus.get(k) is not None]   # Director never carries PAFL
    def field(rec, f, bus): return rec + f[0] + f[1] * bus
    def clear(rec, f): d[rec + f[0]: rec + f[0] + 64 * f[1]] = bytes(64 * f[1])
    def copy(rs, rd, f, b, n):
        s, t = field(rs, f, b), field(rd, f, n); d[t:t + f[1]] = src[s:s + f[1]]
    def strip_rec(r):   # inputs, FX returns, UFX returns
        for f in (GRP, AUXT, MTXT): clear(r, f)
        for b, n, k in bmap:
            f = GRP if k[0] in GROUPISH else AUXT if k[0] in SENDISH else MTXT if k[0] in MTXISH else None
            if f: copy(r, r, f, b, n)
    for i in range(IN_N): strip_rec(IN0 + i * IN_SZ)
    for i in range(FXR_N): strip_rec(FXR0 + i * RET_SZ)
    for i in range(UFXR_N): strip_rec(UFXR0 + i * RET_SZ)
    d[MIX0:MIX0 + MIX_N * MIX_SZ] = bytes(MIX_N * MIX_SZ)
    for b, n, k in bmap:
        rs, rd = MIX0 + b * MIX_SZ, MIX0 + n * MIX_SZ
        d[rd:rd + MIX_SZ] = src[rs:rs + MIX_SZ]
        for f in (M_AUXT, M_MTXT, M_ARR6): clear(rd, f)
        for jb, jn, jk in bmap:
            if k[0] in GROUPISH and jk[0] in SENDISH: copy(rs, rd, M_AUXT, jb, jn)
            copy(rs, rd, M_MTXT, jb, jn); copy(rs, rd, M_ARR6, jb, jn)
    d[FXS0:FXS0 + FXS_N * FXS_SZ] = bytes(FXS_N * FXS_SZ)
    k = min(old["mFX"], new["mFX"]); d[FXS0:FXS0 + k * FXS_SZ] = src[FXS0:FXS0 + k * FXS_SZ]
    k = min(old["sFX"], new["sFX"])
    d[FXS0 + new["mFX"] * FXS_SZ:FXS0 + (new["mFX"] + k) * FXS_SZ] = src[FXS0 + old["mFX"] * FXS_SZ:FXS0 + (old["mFX"] + k) * FXS_SZ]
    if new_cfg_bytes is not None: d[3:16] = new_cfg_bytes
    return d

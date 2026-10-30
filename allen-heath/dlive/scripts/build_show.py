#!/usr/bin/env python3
"""Build a dLive show from a template show + plan JSON.
Writes names/colours, stereo input config, group/DCA/main assigns into EVERY StageBox scene that has the
template's Input Mixer layout, so recalling any stored scene keeps the new channel setup.
Usage: build_show.py plan.json template.tar.gz out.tar.gz
"""
import json, sys, os, io, tarfile, gzip, shutil, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dlive_scene import Scene


def apply(scene, plan, paired=frozenset()):
    """paired: input channels that sit in a linked stereo pair. Director writes byte 7 of each channel block as a mono
    flag (1 mono, 0 a side of a stereo pair; every Director-saved show agrees with InputConfig), so it is kept in step."""
    col = plan["colours"]
    m = scene.mixer()
    for ch in range(1, 129):
        s = m["first"] + (ch - 1) * m["bs"] + m["sec"]
        scene.d[s + 7] = 0 if ch in paired else 1
    for row in plan["inputs"]:
        ch, name, colour, mg, sg, dca = row[:6]
        main = row[6] if len(row) > 6 else 0
        scene.set_name("Input Channel", ch, name, col[colour])
        scene.set_input(ch, mono_groups=mg, st_groups=sg, dca=dca, main=main)
    for k, v in plan["dca_names"].items(): scene.set_name("DCA Channel", int(k), v)
    for k, v in plan.get("stereo_aux_names", {}).items(): scene.set_name("Stereo Aux Channel", int(k), v)


def main(plan_path, template, out):
    plan = json.load(open(plan_path))
    work = tempfile.mkdtemp()
    with tarfile.open(template) as t: t.extractall(work)
    show = os.path.join(work, "Show")
    icp = os.path.join(show, "InputConfig", "InputConfig.dat")
    tok = open(icp).read().split()
    assert tok[0] == "1" and len(tok) == 65, tok[:3]
    flags = tok[1:]
    planned = max(r[0] for r in plan["inputs"])
    for k in range((planned + 1) // 2): flags[k] = "0"
    for odd in plan["stereo_pairs"]:
        assert odd % 2 == 1; flags[(odd - 1) // 2] = "1"
    open(icp, "w").write("1\n" + "\n".join(flags) + "\n")
    paired = frozenset(c for k in range(64) if flags[k] == "1" for c in (2 * k + 1, 2 * k + 2))
    edited = 0
    sdir = os.path.join(show, "Scenes")
    ref_header = None
    for fn in sorted(os.listdir(sdir)):
        if not (fn.startswith("StageBoxScene") and fn.endswith(".tar.gz")): continue
        p = os.path.join(sdir, fn)
        with tarfile.open(p) as t:
            members = t.getmembers(); datas = {m.name: t.extractfile(m).read() for m in members if m.isfile()}
        changed = False
        for name, data in datas.items():
            if b"Input Mixer\x00" not in data or b"Input Channel Name Colour Manager" not in data: continue
            s = Scene(data)
            h = s.mixer()["header"]
            ref_header = ref_header or h
            if h != ref_header: print("skip (different mixer header)", fn); continue
            apply(s, plan, paired); datas[name] = bytes(s.d); changed = True
        if changed:
            buf = io.BytesIO()
            with tarfile.open(fileobj=buf, mode="w:gz", format=tarfile.USTAR_FORMAT) as t:
                for m in members:
                    m.mtime = int(m.mtime); m.pax_headers = {}
                    if m.isfile():
                        m.size = len(datas[m.name]); t.addfile(m, io.BytesIO(datas[m.name]))
                    else: t.addfile(m)
            open(p, "wb").write(buf.getvalue()); edited += 1
    with tarfile.open(template) as src, tarfile.open(out, "w:gz", format=tarfile.USTAR_FORMAT) as dst:
        for m in src.getmembers():
            m.mtime = int(m.mtime); m.pax_headers = {}
            if m.isfile():
                data = open(os.path.join(work, m.name), "rb").read()
                m.size = len(data); dst.addfile(m, io.BytesIO(data))
            else:
                dst.addfile(m)
    shutil.rmtree(work)
    print(f"edited {edited} StageBox scenes -> {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__); sys.exit(0 if len(sys.argv) > 1 else 2)
    main(*sys.argv[1:4])

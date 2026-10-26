#!/usr/bin/env python3
"""metricab_ref.py: write an ADPTR Metric AB preset (.tfx) with the song's demo/reference in slot 1
(index 0), synced to the Pro Tools timeline.

    metricab_ref.py SEED.tfx REF_PATH OUT.tfx

SEED = any preset you saved from Metric AB (Settings menu > Save Settings As). Slots already in the seed
are kept. Save OUT.tfx into the plug-in's preset folder so the Librarian lists it, then load it with
hp_metricab.py. Tested against Metric AB presets whose XML starts at byte 700 after a "VC2!" tag; any
other layout is refused. Two size fields follow the XML header: >I at 636 (bytes from there to EOF)
and <I at 696 (XML length)."""
import re, struct, sys
if len(sys.argv) != 4 or sys.argv[1] in ("-h", "--help"):
    print(__doc__); sys.exit(0 if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help") else 2)
seed, ref, out = sys.argv[1:4]
d = bytearray(open(seed, "rb").read())
x0 = d.find(b"<?xml")
if x0 != 700 or d[692:696] != b"VC2!":
    sys.exit("unexpected tfx layout (save a fresh seed from Metric AB)")
xml = bytes(d[x0:]).rstrip(b"\x00").decode("utf-8")
xml = re.sub(r'<Sample index="0" path="[^"]*"/>', "", xml)
esc = ref.replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;").replace(">", "&gt;")
xml = xml.replace("<SampleManager>", f'<SampleManager><Sample index="0" path="{esc}"/>', 1)
xml = re.sub(r'(<Track0><Parameter name="Track Sync" mapped=")[^"]*"', r'\g<1>2.0"', xml)  # 2 = sync to host timeline
xml = re.sub(r'(<Global>.*?<Parameter name="Selected Track" mapped=")[^"]*"', r'\g<1>0.0"', xml, flags=re.S)
body = xml.encode("utf-8")
i = d.find(b"d_Selected Track\x00\x00")
if i > 0: d[i + 20:i + 28] = struct.pack(">d", 0.0)
new = d[:696] + struct.pack("<I", len(body)) + body + b"\x00"
new[636:640] = struct.pack(">I", len(new) - 636)
open(out, "wb").write(new)
print("wrote", out, len(new))

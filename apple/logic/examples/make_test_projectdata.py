#!/usr/bin/env python3
"""Write a tiny synthetic ProjectData file for testing logic_pd.py without a real project.

usage: make_test_projectdata.py OUT

It holds three strips that follow the layout in ../references/PROJECTDATA.md:
  1 "Audio 1"  live input 1 -> Bus 1, inserts DemoComp, DemoEQ (made-up AUs)
  2 "Audio 2"  live input 2 -> output value 73 (the "main out" default of logic_pd.py paths)
  3 "Aux 1"    Bus 1 -> output value 73, insert DemoLimit
Logic will not open this file. It only exercises the parser and the delay patcher.

Smoke test (from the logic/ folder):
  python3 examples/make_test_projectdata.py /tmp/PD
  python3 scripts/logic_pd.py strips /tmp/PD
  python3 scripts/logic_pd.py extract /tmp/PD /tmp/plists     # names match examples/lat.txt
  python3 scripts/logic_pd.py paths /tmp/PD --lat examples/lat.txt --json /tmp/paths.json
  python3 scripts/logic_pd.py plan /tmp/paths.json            # same as examples/plan.json
  python3 scripts/logic_pd.py add-delay /tmp/PD /tmp/PD2 examples/plan.json
  python3 scripts/logic_pd.py strips /tmp/PD2
"""
import plistlib
import struct
import sys

SIG_AUDIO = b"\xab\xf7\xd3\xcf"
SIG_AUX = b"\xab\xf5\xd7\xcf"


def chunk(tag, ch, slot, payload):
    h = bytearray(36)
    h[:4] = tag
    struct.pack_into("<I", h, 14, ch)
    struct.pack_into("<I", h, 18, slot)
    struct.pack_into("<Q", h, 28, len(payload))
    return bytes(h) + payload


def strip(name, sig, inn, out):
    pl = bytearray(0xD0)
    n = name.encode()
    pl[0x3D:0x3D + len(n)] = n
    pl[0x4C:0x50] = sig
    struct.pack_into("<HH", pl, 0x5C, out, inn)
    return bytes(pl)


def au(ch, slot, name, subtype):
    c = bytearray(0xD0)
    c[0x2A] = slot - 5
    n = name.encode() + b"\0"
    c[0x9C:0x9C + len(n)] = n
    p = plistlib.dumps({"type": 0x61756678, "subtype": subtype, "manufacturer": 0x44656D6F,
                        "name": "x", "version": 0}, fmt=plistlib.FMT_XML) + b"\n"
    p += b"\0" * ((-len(p)) % 4)
    struct.pack_into("<I", c, 0xBC, len(p))
    c = bytes(c) + p + bytes(20)
    return chunk(b"UCuA", ch, slot, c[36:])


def main(out):
    body = chunk(b"OCuA", 1, 0xFFFFFFFF, strip("Audio 1", SIG_AUDIO, 0, 33))
    body += au(1, 5, "DemoComp", 0x636D7031) + au(1, 6, "DemoEQ", 0x65713031)
    body += chunk(b"OCuA", 2, 0xFFFFFFFF, strip("Audio 2", SIG_AUDIO, 1, 73))
    body += chunk(b"OCuA", 3, 0xFFFFFFFF, strip("Aux 1", SIG_AUX, 33, 73)) + au(3, 5, "DemoLimit", 0x6C696D31)
    hdr = bytearray(24)
    struct.pack_into("<Q", hdr, 16, len(body))
    open(out, "wb").write(bytes(hdr) + body)
    print("wrote", out)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0 if len(sys.argv) == 2 else 2)
    main(sys.argv[1])

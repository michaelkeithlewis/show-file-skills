#!/usr/bin/env python3
"""Avid VENUE / D-Show show file (.dsh) reader and safe channel-name patcher.

The file starts with the magic string "Digidesign Storage - 1.0" and continues as a
serialized tree of typed tokens. See ../references/FORMAT.md.

Commands:
  dshow_tool.py dump  SHOW.dsh                 system config + every channel name
  dshow_tool.py names SHOW.dsh                 one strip per line: slot, id, name
  dshow_tool.py rename SHOW.dsh OLD NEW OUT.dsh [--pad space|nul] [--dry-run]

Rename rule: NEW must be the same length as OLD or shorter. The tool replaces every
NUL-terminated copy of OLD (a whole string, not the tail of a longer one) and pads
NEW to the same byte length, so no offset in the file moves. The default pad is
spaces before the NUL, which keeps the packed name tables parsing the same way.
"--pad nul" pads with NUL bytes instead (the older method; see FORMAT.md for the risk).
The output size must equal the input size, or the tool refuses to write.
"""
import argparse
import re
import struct
import sys

MAGIC = b"Digidesign Storage - 1.0"
SZ = {0x01: 1, 0x03: 1, 0x06: 4, 0x0B: 4}
STRIP = re.compile(rb"\x0aStrip\x00\x0d(.{4})(.)", re.S)


def load(path):
    data = open(path, "rb").read()
    if MAGIC not in data[:64]:
        sys.exit("%s: no 'Digidesign Storage' magic, not a VENUE show file" % path)
    return data


def cstr(data, i):
    j = data.index(b"\0", i)
    return data[i:j].decode("latin1"), j + 1


def dump_config(data):
    """Leading key/value block: 0x0a key, then a typed value (string or int)."""
    _, i = cstr(data, 1)
    out, key = [], None
    while i < len(data):
        t = data[i]
        if t == 0x0A:
            s, j = cstr(data, i + 1)
            if key is not None:
                out.append((key, s))
                key = None
            else:
                key = s
            i = j
        elif t in SZ:
            sz = SZ[t]
            v = struct.unpack_from("<I", data, i + 1)[0] if sz == 4 else data[i + 1]
            if key is not None:
                out.append((key, v))
                key = None
            i += 1 + sz
        else:
            break
    return out


def strips(data):
    """(slot index, strip id, flag, name) for every 'Strip' object."""
    rows = []
    for k, m in enumerate(STRIP.finditer(data)):
        sid = struct.unpack("<I", m.group(1))[0]
        name, _ = cstr(data, m.end())
        rows.append((k, sid, m.group(2)[0], name))
    return rows


def occurrences(data, name):
    """Offsets of whole NUL-terminated copies of name (preceding byte not printable)."""
    tok = name.encode("latin1") + b"\0"
    out = []
    for m in re.finditer(re.escape(tok), data):
        p = m.start()
        if p > 0 and 0x20 <= data[p - 1] <= 0x7E:
            continue
        out.append(p)
    return out


def rename(data, old, new, pad="space"):
    if not old or not new:
        raise ValueError("names must not be empty")
    if len(new.encode("latin1")) > len(old.encode("latin1")):
        raise ValueError("new name is longer than old name, not offset-safe (use the VENUE software)")
    if "\0" in new:
        raise ValueError("new name contains NUL")
    ob, nb = old.encode("latin1"), new.encode("latin1")
    fill = b" " if pad == "space" else b"\0"
    rep = nb + fill * (len(ob) - len(nb)) + b"\0" if pad == "space" else nb + b"\0" + fill * (len(ob) - len(nb))
    assert len(rep) == len(ob) + 1
    offs = occurrences(data, old)
    buf = bytearray(data)
    for p in offs:
        buf[p:p + len(rep)] = rep
    return bytes(buf), offs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("dump", help="system config and unique channel names")
    d.add_argument("show")
    n = sub.add_parser("names", help="every strip slot with its id and name")
    n.add_argument("show")
    r = sub.add_parser("rename", help="same-length-or-shorter rename, writes a new file")
    r.add_argument("show")
    r.add_argument("old")
    r.add_argument("new")
    r.add_argument("out")
    r.add_argument("--pad", choices=("space", "nul"), default="space")
    r.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    data = load(a.show)
    if a.cmd == "dump":
        print("== SYSTEM CONFIG ==")
        for k, v in dump_config(data):
            print("  %-28s %s" % (k, v))
        rows = strips(data)
        uniq = []
        for _, _, _, nm in rows:
            if nm and nm not in uniq:
                uniq.append(nm)
        print("\n== STRIPS: %d slots, %d unique names ==" % (len(rows), len(uniq)))
        print("  " + ", ".join(uniq))
    elif a.cmd == "names":
        for k, sid, flag, nm in strips(data):
            print("%4d  id %-6d flag %d  %s" % (k, sid, flag, nm))
    else:
        if a.out == a.show:
            sys.exit("refusing to overwrite the input, write a new file")
        if a.old not in {nm for _, _, _, nm in strips(data)}:
            sys.exit("%r is not a strip name in this show (run 'names')" % a.old)
        try:
            nd, offs = rename(data, a.old, a.new, a.pad)
        except ValueError as e:
            sys.exit(str(e))
        if len(nd) != len(data):
            sys.exit("size changed, not writing")
        changed = sum(1 for x, y in zip(data, nd) if x != y)
        print("%r -> %r: %d place(s) at %s, %d bytes changed" % (a.old, a.new, len(offs), offs, changed))
        if a.dry_run:
            print("dry run, nothing written")
            return
        open(a.out, "wb").write(nd)
        print("wrote %s (size %d, unchanged)" % (a.out, len(nd)))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""List or drop the stored scenes of a dLive show (firmware 2.x, show Version 14).

A show keeps its live state in Show/Scenes/StageBoxScene65535.tar.gz (MixRack) and SurfaceScene65535.tar.gz
(surface). Every other StageBox/Surface scene file is a stored scene. Director enumerates the scene files that are
present (factory shows skip numbers), so no other file indexes them, and removing a stored scene is removing its
two files.

A template show carries its old artist's stored scenes. They keep the old mixer config and processing, and a recall
puts them back on the desk, so a new show built from a template is safer with the live state only.

usage:
  dlive_scenes.py dump <show.tar.gz>
  dlive_scenes.py drop <show.tar.gz> <out.tar.gz> [--keep 1,2,5]   (drop every stored scene except --keep)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dlive_mix import read_show, write_show  # noqa: E402

SCENE = re.compile(r"Show/Scenes/(StageBox|Surface)Scene(\d+)\.tar\.gz$")
LIVE = 65535


def scenes(files):
    """{number: [file names]} of every scene file in the show."""
    out = {}
    for n in files:
        m = SCENE.search(n)
        if m:
            out.setdefault(int(m.group(2)), []).append(n)
    return out


def dump(path):
    _, files = read_show(path)
    sc = scenes(files)
    for num in sorted(sc):
        kinds = sorted(SCENE.search(n).group(1) for n in sc[num])
        size = sum(len(files[n]) for n in sc[num])
        print("%-6s %-18s %8d bytes%s" % (num, "+".join(kinds), size, "   (live state)" if num == LIVE else ""))
    print("%d stored scene(s)" % len([n for n in sc if n != LIVE]))


def drop(path, out, keep=()):
    if os.path.abspath(path) == os.path.abspath(out):
        sys.exit("write a new file; never overwrite the source show")
    members, files = read_show(path)
    sc = scenes(files)
    live = sc.get(LIVE, [])
    if not any("StageBox" in n for n in live) or not any("Surface" in n for n in live):
        sys.exit("no live StageBox + Surface scene (65535) in this show; refusing")
    gone = {n for num, names in sc.items() if num != LIVE and num not in keep for n in names}
    members = [m for m in members if m.name not in gone]
    for n in gone:
        files.pop(n, None)
    write_show(members, files, out)
    print("dropped %d stored scene file(s), kept the live state%s -> %s" % (
        len(gone), " and scenes %s" % ",".join(map(str, sorted(keep))) if keep else "", out))
    print("run dlive_lint.py on the result")


def main(argv):
    if len(argv) < 3 or argv[1] not in ("dump", "drop") or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0 if len(argv) > 1 and argv[1] in ("-h", "--help") else 2
    if argv[1] == "dump":
        dump(argv[2])
    else:
        if len(argv) < 4:
            print(__doc__)
            return 2
        keep = ()
        if "--keep" in argv:
            keep = {int(x) for x in argv[argv.index("--keep") + 1].split(",") if x.strip()}
        drop(argv[2], argv[3], keep)
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)
    sys.exit(main(sys.argv))

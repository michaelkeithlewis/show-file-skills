#!/usr/bin/env python3
"""Build a LiveTrax 3 session template from a track list.

LiveTrax (Ardour's live recorder) saves sessions and templates as Ardour XML
(Session version 7003). A template is a session with no Sources/Regions and
empty playlists. This script clones the track and Master structure of a base
template that LiveTrax itself wrote, then rebuilds the track list from a CSV.

CSV columns (header row required):
  name      track name (unique, no "/")
  inputs    capture channels, "5" or "57-58" (stereo = two channels)
  playback  direct-out (virtual soundcheck) channels, same form, blank = none
  arm       1 = record-armed (default 1)
  color     hex RRGGBB, blank = LiveTrax default blue
  master    1 = feed the Master bus (default 0)
  mute      1 = muted (default 0)

Port connections are stored per audio device ("CoreAudio;;<device name>").
A device not listed with --device opens with every track unpatched, so list
every interface the template might be opened on.

Usage:
  lt_template.py BASE.template TRACKS.csv OUT.template --name "Show Name" \
      --device "Dante Virtual Soundcard" --device "<your interface>" \
      [--master-out 59-60]

BASE must be a template or session that LiveTrax itself saved, with a Master bus and
at least one mono track. The script clones that mono track for every row. Run
lt_dump.py on a saved session to read the exact CoreAudio device names.
"""
import argparse
import copy
import csv
import re
import sys
import time
import xml.etree.ElementTree as ET

DEFAULT_COLOR = 0x5577D7FF


def chans(s):
    s = (s or "").strip()
    if not s:
        return []
    if "-" in s:
        a, b = s.split("-")
        return list(range(int(a), int(b) + 1))
    return [int(s)]


class Ids:
    def __init__(self, start):
        self.n = start

    def next(self):
        self.n += 1
        return str(self.n)


def max_id(root):
    m = 0
    for e in root.iter():
        v = e.get("id", "")
        if v.isdigit():
            m = max(m, int(v))
    return m


def set_ext(port, devices, other):
    """Replace a port's ExtConnections: one empty entry per device, plus the target."""
    for e in list(port):
        if e.tag in ("ExtConnection", "Connection"):
            port.remove(e)
    for d in devices:
        ET.SubElement(port, "ExtConnection", {"for": "CoreAudio;;" + d})
        if other:
            ET.SubElement(port, "ExtConnection", {"for": "CoreAudio;;" + d, "other": other})


def resize_ports(io, n, track, kind):
    """Give an IO exactly n ports named '<track>/<kind> k', cloning the first port."""
    ports = io.findall("Port")
    proto = ports[0]
    for p in ports:
        io.remove(p)
    insert_at = 0
    for k in range(1, n + 1):
        p = copy.deepcopy(proto)
        p.set("name", "%s/%s %d" % (track, kind, k))
        io.insert(insert_at, p)
        insert_at += 1
    return io.findall("Port")


def rename(route, old, new):
    for e in route.iter():
        for a in ("name", "output"):
            v = e.get(a)
            if v is None:
                continue
            if v == old:
                e.set(a, new)
            elif v.startswith(old + "/"):
                e.set(a, new + v[len(old):])
            elif v in ("recorder:" + old, "player:" + old):
                e.set(a, v.split(":")[0] + ":" + new)


def renumber(route, ids):
    """Fresh unique ids for every numeric id inside a cloned route. Returns old->new map."""
    m = {}
    for e in route.iter():
        v = e.get("id", "")
        if v.isdigit() and e.tag not in ("Button",):
            m[v] = ids.next()
            e.set("id", m[v])
    return m


def build_track(proto, row, order, ids, devices, bitslot):
    r = copy.deepcopy(proto)
    old = r.get("name")
    name = row["name"]
    rename(r, old, name)
    renumber(r, ids)
    ins = chans(row["inputs"])
    outs = chans(row.get("playback"))
    nch = len(ins)

    r.find("PresentationInfo").set("order", str(order))
    color = (row.get("color") or "").strip().lstrip("#")
    r.find("PresentationInfo").set("color", str(int(color + "ff", 16) if color else DEFAULT_COLOR))

    in_io = [i for i in r.findall("IO") if i.get("direction") == "Input"][0]
    for k, p in enumerate(resize_ports(in_io, nch, name, "audio_in")):
        set_ext(p, devices, "system:capture_%d" % ins[k])

    out_io = [i for i in r.findall("IO") if i.get("direction") == "Output"][0]
    to_master = (row.get("master") or "0").strip() == "1"
    for k, p in enumerate(out_io.findall("Port")):
        for e in list(p):
            p.remove(e)
        if to_master:
            ET.SubElement(p, "Connection", {"other": "Master/audio_in %d" % (k + 1)})

    for pr in r.findall("Processor"):
        if pr.get("role") == "DirectOuts":
            pr.set("bitslot", str(bitslot))
            dio = pr.find("IO")
            for k, p in enumerate(resize_ports(dio, nch, name, "audio_send")):
                set_ext(p, devices, "system:playback_%d" % outs[k] if k < len(outs) else None)
            ps = pr.find("PannerShell")
            for pn in ps.findall("Panner"):
                ps.remove(pn)
            if nch == 2:
                ET.SubElement(ps, "Panner", {"uri": "http://ardour.org/plugin/panner_balance", "type": "Stereo Balance"})

    phase = [c for c in r.findall("Controllable") if c.get("name") == "phase"][0]
    phase.set("phase-invert", "0" * nch)

    mute = (row.get("mute") or "0").strip() == "1"
    r.find("MuteMaster").set("muted", "1" if mute else "0")
    for c in r.findall("Controllable"):
        if c.get("name") == "mute":
            c.set("value", "1" if mute else "0")
        if c.get("name") == "rec-enable":
            c.set("value", "1" if (row.get("arm") or "1").strip() != "0" else "0")
    return r


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("base")
    ap.add_argument("tracks")
    ap.add_argument("out")
    ap.add_argument("--name", required=True)
    ap.add_argument("--device", action="append", required=True)
    ap.add_argument("--master-out", default="", help="Master output channels, blank = unpatched")
    a = ap.parse_args()

    tree = ET.parse(a.base)
    root = tree.getroot()
    if root.get("version") != "7003":
        sys.exit("base is Session version %s, script was decoded against 7003" % root.get("version"))
    rows = list(csv.DictReader(open(a.tracks, newline="")))
    names = [x["name"] for x in rows]
    if len(set(names)) != len(names) or any("/" in n for n in names):
        sys.exit("track names must be unique and contain no '/'")

    routes = root.find("Routes")
    all_routes = list(routes)
    master = [x for x in all_routes if "MasterOut" in x.find("PresentationInfo").get("flags")][0]
    mono = [x for x in all_routes if x is not master and len([p for i in x.findall("IO") if i.get("direction") == "Input" for p in i]) == 1][0]

    ids = Ids(max_id(root) + 1000)
    for x in all_routes:
        if x is not master:
            routes.remove(x)
    playlists = root.find("Playlists")
    pl_proto = copy.deepcopy(playlists[0])
    for p in list(playlists):
        playlists.remove(p)
    for p in list(root.find("UnusedPlaylists")):
        root.find("UnusedPlaylists").remove(p)

    stamp = time.strftime("%Y-%m-%d %H.%M.%S")
    for order, row in enumerate(rows, start=1):
        t = build_track(mono, row, order, ids, a.device, order)
        plid = ids.next()
        t.set("audio-playlist", plid)
        routes.append(t)
        pl = copy.deepcopy(pl_proto)
        pl.attrib.update({"id": plid, "name": row["name"], "orig-track-id": t.get("id"), "pgroup-id": stamp})
        for c in list(pl):
            pl.remove(c)
        playlists.append(pl)

    feeders = [r["name"] for r in rows if (r.get("master") or "0").strip() == "1"]
    m_in = [i for i in master.findall("IO") if i.get("direction") == "Input"][0]
    for k, p in enumerate(m_in.findall("Port")):
        for e in list(p):
            p.remove(e)
        for f in feeders:
            ET.SubElement(p, "Connection", {"other": "%s/audio_out %d" % (f, k + 1)})
    mo = chans(a.master_out)
    m_out = [i for i in master.findall("IO") if i.get("direction") == "Output"][0]
    for k, p in enumerate(m_out.findall("Port")):
        set_ext(p, a.device, "system:playback_%d" % mo[k] if k < len(mo) else None)

    extra = root.find("Extra")
    if extra is not None:
        for ui in extra.iter("UI"):
            for w in list(ui):
                if w.tag == "Window" and re.match(r"RPM-\d+", w.get("name", "")):
                    ui.remove(w)
        for g in extra.iter("GUIObjectState"):
            for o in list(g):
                g.remove(o)

    for o in root.find("Config"):
        if o.get("name") == "take-name":
            o.set("value", "Take1")
    root.set("id-counter", str(ids.n + 100))

    ET.indent(tree, "  ")
    tree.write(a.out, encoding="UTF-8", xml_declaration=True)
    print("wrote %s: %d tracks, master <- %s, id-counter %s" % (a.out, len(rows), feeders or "none", root.get("id-counter")))


if __name__ == "__main__":
    main()

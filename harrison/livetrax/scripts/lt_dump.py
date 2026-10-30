#!/usr/bin/env python3
"""Print the track list and patch of a LiveTrax 3 session or template (Ardour XML).

Usage:
  lt_dump.py SESSION.ardour|NAME.template [--csv OUT.csv]

Prints the audio devices the file has port connections for (the exact CoreAudio
names to pass to lt_template.py --device), then one line per track: order, name,
capture channels, direct-out (playback) channels, record arm, mute, Master feed and
colour. Channels are read from the first device that has a connection on the port.

--csv writes the same rows in the lt_template.py CSV format, so a session that
LiveTrax saved can be edited as a CSV and rebuilt.
"""
import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET


def port_targets(port):
    """{device: target} for one port's ExtConnection entries."""
    out = {}
    for e in port.findall("ExtConnection"):
        dev = e.get("for", "")
        if e.get("other"):
            out.setdefault(dev, e.get("other"))
    return out


def chan_range(nums):
    if not nums:
        return ""
    if len(nums) == 1:
        return str(nums[0])
    if nums == list(range(nums[0], nums[-1] + 1)):
        return "%d-%d" % (nums[0], nums[-1])
    return ",".join(str(n) for n in nums)


def channels(ports, prefix, devices):
    nums = []
    for p in ports:
        t = port_targets(p)
        for d in devices:
            if d in t:
                m = re.match(prefix + r"(\d+)$", t[d])
                if m:
                    nums.append(int(m.group(1)))
                break
    return nums


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session")
    ap.add_argument("--csv", help="write the tracks as an lt_template.py CSV")
    a = ap.parse_args()

    root = ET.parse(a.session).getroot()
    if root.tag != "Session":
        sys.exit("not an Ardour/LiveTrax session file")
    pv = root.find("ProgramVersion")
    print("Session version %s, %s" % (root.get("version"), pv.get("modified-with") if pv is not None else "?"))
    if root.get("version") != "7003":
        print("warning: lt_template.py was decoded against version 7003")

    devices = []
    for e in root.iter("ExtConnection"):
        d = e.get("for", "")
        if d not in devices:
            devices.append(d)
    print("devices with port connections:")
    for d in devices:
        print("  " + d)

    routes = list(root.find("Routes"))
    master = [r for r in routes if "MasterOut" in r.find("PresentationInfo").get("flags", "")]
    feeders = set()
    if master:
        for io in master[0].findall("IO"):
            if io.get("direction") == "Input":
                for p in io.findall("Port"):
                    for c in p.findall("Connection"):
                        feeders.add(c.get("other", "").split("/")[0])

    rows = []
    for r in sorted(routes, key=lambda x: int(x.find("PresentationInfo").get("order", "0"))):
        if master and r is master[0]:
            continue
        name = r.get("name")
        in_io = [i for i in r.findall("IO") if i.get("direction") == "Input"]
        ins = channels(in_io[0].findall("Port"), "system:capture_", devices) if in_io else []
        outs = []
        for pr in r.findall("Processor"):
            if pr.get("role") == "DirectOuts" and pr.find("IO") is not None:
                outs = channels(pr.find("IO").findall("Port"), "system:playback_", devices)
        ctl = {c.get("name"): c.get("value") for c in r.findall("Controllable")}
        col = int(r.find("PresentationInfo").get("color", "0"))
        rows.append({
            "name": name,
            "inputs": chan_range(ins),
            "playback": chan_range(outs),
            "arm": "1" if ctl.get("rec-enable") == "1" else "0",
            "color": "%06x" % (col >> 8),
            "master": "1" if name in feeders else "0",
            "mute": "1" if ctl.get("mute") == "1" else "0",
        })

    print("\n%-4s %-24s %-8s %-8s arm mute master color" % ("#", "name", "in", "direct"))
    for k, x in enumerate(rows, 1):
        print("%-4d %-24s %-8s %-8s %-3s %-4s %-6s %s" % (k, x["name"], x["inputs"] or "-", x["playback"] or "-",
                                                         x["arm"], x["mute"], x["master"], x["color"]))
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["name", "inputs", "playback", "arm", "color", "master", "mute"])
            w.writeheader()
            w.writerows(rows)
        print("\nwrote %s" % a.csv)


if __name__ == "__main__":
    main()

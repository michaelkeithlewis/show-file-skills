# Behringer X-Air

Notes on Behringer X-Air scenes (`.scn`) for the XR18, XR16 and XR12, opened in X-AIR-Edit. A scene is a text
file. The X32 and M32 share a similar text grammar and are covered in [`behringer/x32`](../x32/README.md).

This folder is documentation only. There is no X-Air reader or writer in this repo.

## Safety

The format is not documented here by Behringer. Never load a generated scene straight into a mixer. Open it in
X-AIR-Edit, check it, save it from the editor, and load only that save. Do the first load at prep, never at the
show.

## What we know

- A generated XR18 scene loaded in X-AIR-Edit and showed the written names, colours, stereo pair arrows and 48V badges on the right channels (X-AIR-Edit, version not recorded, 2026-08-23).
- A pair of captures that differ in one phantom switch fixed which channel a 48V setting belongs to in the head-amp section (single-change capture pair, XR18).
- The one single-change capture on file for the compressor moves only its on and off switch. Every other X-Air capture shows the factory compressor values (committed captures, 2026-09-02).

## What we don't know

- The compressor values. No X-Air capture holds a non-default threshold, ratio, knee, gain, attack or release, so the mapping is carried over from the X32 and M32 and is unconfirmed on X-Air. A factory save plus a second save with one channel changed would settle it (2026-09-02).
- XR16 and XR12. They use an XR18 template and have no file set of their own, so they are not proven.
- Whether a mixer loads a generated scene. Nothing here ran on an XR18.
- Channel colour when two channels swap places. A measured case kept each slot's old colour under the arriving name. A fix is in progress and the case stays open (2026-09-02, 2026-09-03).

## Session notes

*Add a dated line here after every session: `YYYY-MM-DD, firmware, what you found.`*

2026-08-23, X-AIR-Edit, a generated XR18 scene loaded with names, colours, pairs and 48V badges.

2026-09-02, committed captures, the only compressor single-change is the on and off switch.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack
planning app for touring and production crews.

Full list of contributors: [Contributors](https://github.com/michaelkeithlewis/show-file-skills#contributors).

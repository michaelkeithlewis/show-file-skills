# What the editor accepts

What X32-Edit and X-AIR-Edit do with a generated scene. One fact per line, each ending with its proof: editor and version, console if hardware, date. "Version not recorded" means the session did not write the version down. A generated scene is a file written by a tool, not saved by the editor. Format details are in `FORMAT.md`.

## What loads

- A generated scene with names, colours, a stereo pair badge and EQ, gate and compressor settings loaded and showed all of them, including on channels the source scene held no records for. (X32-Edit, version not recorded, 2026-08-23)
- A scene whose section order matches the file it was built from loads with its processing intact. Firmware 2.7 scenes put the channel blocks last and firmware 4.0 scenes put them first, so the source file's order is the only safe order. (desk-written scenes of both firmware lines, byte compare, 2026-08-14)
- A desk-written M32 scene that interleaves channel blocks and global sections is a real M32 form, accepted by its owner. A tool must keep that order, not rearrange it. (M32 scene saved on a desk, round trip byte-identical, 2026-08-14)
- A no-edit round trip of five desk-written X32 and M32 scenes, covering both firmware section orders, comes back byte-identical. (desk-written files, byte compare, 2026-08-14)
- Generated X32 scenes have loaded on real X32 hardware. (X32 console, firmware and date not recorded, before 2026-08-30)
- X-AIR-Edit loaded a round-tripped desk-written scene and showed names, colours, pair arrows and 48V badges on five channels. (X-AIR-Edit, version not recorded, 2026-08-23)

## What is silently dropped

- X32-Edit gives no error when a scene lists the global sections before the channel blocks. It discards all channel processing and shows blank EQ. (X32-Edit, version not recorded, found by loading one generated scene by hand, 2026-08-13)
- A channel with no record in a partial scene keeps whatever the editor already holds for it. The scene does not clear it. (X32-Edit, version not recorded, 2026-08-23)
- Phantom power belongs to the input socket, not the channel. When two channels are fed from one socket, only the first shows 48V, and switching 48V on the second changes nothing in the file. (scene text read after export, no editor load, 2026-09-03)
- A round trip that wrote one fallback colour onto every channel of an X-Air scene destroyed the engineer's colours. Colours must come from the file that was loaded. (desk-written X-Air scene, 2026-08-13)

## What is refused

- No X32-Edit or X-AIR-Edit refusal of a generated scene is recorded in the sources for this file.

## Name and character limits

- A blank channel stays blank in the file. A generated scene that writes a placeholder such as "Ch 30" into it puts a name on the desk that the engineer never typed. The label is a display decision. (desk-written X32 and X-Air scenes compared with generated ones, 2026-08-13)
- A scene label that the source file carries is kept as it is. A generated scene must not replace it with a tool or product name. (desk-written scene label compared after round trip, 2026-08-13)

## Empty and partial files

- A partial scene is valid. X32-Edit applies the records the scene has and leaves every other channel as it was. (X32-Edit, version not recorded, 2026-08-23)

## Version and firmware notes

- Firmware 2.7 and 4.0 order the channel blocks differently, and both are real. A writer must follow the order of the file it loaded, never one fixed order. (desk-written scenes, 2026-08-14)
- An XR18 scene holds 16 input strips. Channels beyond 16 are not in the file. (XR18 scene built from a 40-channel show, file text read, 2026-09-03)
- XR16 and XR12 scenes built from the XR18 form have not been loaded in an editor. (no X-AIR-Edit load recorded for either model, as of 2026-10-18)

# show-file-skills

Read and write live audio show files and studio sessions without the vendor software open.
Built on tour by Michael Lewis, a touring FOH and monitor engineer and co-founder of
[Truck Packer](https://truckpacker.com).

Every format here was decoded by hand on real gigs: a console file had to be built on a
day off, a session had to be prepped on a bus, a recording rig had to match the console
patch. This repo holds the tools and the notes so you do not have to decode them again.

## Use it in the browser

The `digico/`, `dlive/`, `yamaha/` and `venue/` folders power [I Don't Own a PC](https://idontownapc.com), a free
web tool built on this code. Drop an input list or a show file and edit it on a console view in the
browser: [DiGiCo sessions](https://idontownapc.com), [dLive shows](https://idontownapc.com/dlive),
[Yamaha CL, QL and DM7 shows](https://idontownapc.com/yamaha) and [Avid S6L shows](https://idontownapc.com/s6l). The
[DiGiCo Session Converter](https://idontownapc.com/digico-session-converter) writes a session for older DiGiCo
software, which DiGiCo's SD & Q Convert can't do.

## Formats

| Folder | Format | What you can do |
| --- | --- | --- |
| [`dlive/`](dlive/) | Allen & Heath dLive show (`.tar.gz`, firmware 2.x) | Names, colours, patch, mixer config, mixes and sends, processing, preamps, SoftKeys, layout, plus a validator |
| [`digico/`](digico/) | DiGiCo SD and Quantum session (`.ses`) | Read any session, build and edit sessions from an input list or plain description on an editor-made baseline |
| [`protools/`](protools/) | Avid Pro Tools (PTSL scripting) | Drive a running session: transport, tracks, markers, routing, import, bounce, session prep and stem QC |
| [`logic/`](logic/) | Apple Logic Pro `ProjectData` | Read channel strips, insert slots and routing, measure plug-in latency, bounce through Accessibility |
| [`livetrax/`](livetrax/) | LiveTrax 3 (Ardour XML) | Generate multitrack record templates from an input list |
| [`liveprofessor/`](liveprofessor/) | LiveProfessor `.rack2` (JUCE ValueTree) | Read, write and generate pre-routed sessions byte-exact |
| [`venue/`](venue/) | Avid VENUE `.dsh`: S6L, and classic D-Show, Profile and SC48 | Read a whole S6L show, plug-in racks included. On VENUE 8.2 shows: names, faders, colours and rack slot clears, each loaded back in VENUE Standalone. Classic shows: config and strip names |
| [`yamaha/`](yamaha/) | Yamaha CL and QL (`.CLF`), DM7 and DM5 (`.dm7f`, `.dmxf`), DM3 and TF | Read the show. On CL, QL and DM7 V2.01: names, colours, faders, ON keys, HPF, input patch and head amps, each loaded back in the Yamaha editor |
| [`macos-accessibility/`](macos-accessibility/) | macOS Accessibility (AX) | Drive Logic, Pro Tools and save panels by name, with no screenshots or mouse |

Each folder is a [Claude Code](https://claude.com/claude-code) skill: copy it into
`~/.claude/skills/` and ask for what you need ("set up the IEM sends in my dLive show",
"build a Q225 session from this input list"). Every folder also works without Claude:
the scripts are plain Python and each folder README shows the commands.

## Safety

These formats are not documented by the manufacturers. Never load a generated file straight
into a console. Open it in the offline editor, check it, save it from the editor, and load
only that save. Do the first load at prep or rehearsal, never at the show, and keep a
known-good show on a USB stick.

## Why this lives next to Truck Packer

[Truck Packer](https://truckpacker.com) plans the truck pack for touring and production
crews: your cases, your trucks, a 3D load plan the whole crew can open. This repo comes
from the same place: engineers on the road who would rather build the show file and the
truck pack before load-in than at it. If you advance tours, try
[Truck Packer](https://truckpacker.com).

## Contributing

Found a field we got wrong, or a firmware we have not seen? Open an issue with the console,
the firmware or software version, and what you expected. Do not attach show files that
belong to someone else.

## License and trademarks

MIT, see [LICENSE](LICENSE). No warranty. This project is not affiliated with or endorsed by
Allen & Heath, DiGiCo, Avid, Yamaha, Apple, Harrison, Ardour or the makers of LiveProfessor. All
product names are trademarks of their owners. Part of the dLive field map credits
[jaylenjinx/dlive-show-editor](https://github.com/jaylenjinx/dlive-show-editor).

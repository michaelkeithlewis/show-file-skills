# LiveTrax 3 session and template format notes

LiveTrax is the live multitrack recorder built on Ardour. It is not Waves Tracks Live.
LiveTrax 3 saves sessions (`.ardour`) and templates (`.template`) as Ardour XML.
These notes were checked against files written by LiveTrax 3.0-5, `Session version="7003"`.

## Where templates live (macOS)

```
~/Library/Preferences/LiveTrax3/templates/<Name>/<Name>.template
```

LiveTrax 1 templates sit in the `LiveTrax1/` folder next to it. A template folder holds
one `.template` file with the same name as the folder.

## Template vs session

A template is a session with no audio: `Sources` and `Regions` are empty and every
playlist has no regions. Everything else (routes, ports, config, control protocols)
is the same as in a session.

## Top-level elements of `<Session>`

`ProgramVersion` (created-with / modified-with), `MIDIPorts`, `Config` (a list of
`<Option name= value=>`, for example `take-name`), `Metadata`, `Sources`, `Regions`,
`Locations`, `Bundles`, `VCAManager`, `Routes`, `Playlists`, `UnusedPlaylists`,
`RouteGroups`, `Speakers`, `TempoMap`, `ControlProtocols`, `Extra` (GUI state),
`Script`, `IOPlugins`.

Session attributes include `id-counter`. Every object id in the file must be below it.
After you add objects, set `id-counter` above the highest id.

## Routes

`Routes` holds one `Route` per track plus the Master bus.

- The Master route has `PresentationInfo flags="MasterOut,OrderSet"` and `order="0"`.
- A track route has `PresentationInfo order="N"` (1-based display order) and
  `color` (RGBA packed in one unsigned 32-bit integer, for example `0x5577D7FF`).
- The route attribute `audio-playlist` holds the id of its playlist in `Playlists`.
  The playlist carries `orig-track-id` (the route id) and `name` (the track name).

Inside a track route:

| Element | What it holds |
|---|---|
| `IO direction="Input"` | one `Port` per recorded channel, named `<track>/audio_in k` |
| `IO direction="Output"` | two ports `<track>/audio_out 1-2`. `Connection other="Master/audio_in k"` when the track feeds Master |
| `Processor name="recorder:<track>"` / `player:<track>` | disk writer and reader |
| `Processor role="DirectOuts"` | the direct-out send. Its own `IO` has one port per channel, `<track>/audio_send k`. Attribute `bitslot` must be unique per track |
| `Controllable name="rec-enable"` | `value="1"` = armed |
| `Controllable name="mute"` + `MuteMaster muted=` | mute state (set both) |
| `Controllable name="phase"` | `phase-invert` = one `0`/`1` character per channel |

A stereo track has two input ports and two direct-out ports. Its direct-out
`PannerShell` uses `Panner type="Stereo Balance"` (`uri="http://ardour.org/plugin/panner_balance"`).

## Port connections are stored per audio device

Hardware connections are not stored once. Each port carries one `ExtConnection` entry
per audio device it has seen:

```xml
<Port name="Kick/audio_in 1" type="audio" direction="Input">
  <ExtConnection for="CoreAudio;;Dante Virtual Soundcard"/>
  <ExtConnection for="CoreAudio;;Dante Virtual Soundcard" other="system:capture_1"/>
</Port>
```

- `for` is `CoreAudio;;<device name>`. The device name must match the CoreAudio name
  exactly.
- `other="system:capture_N"` is hardware input N. `other="system:playback_N"` is hardware
  output N.
- If the device you open the template on is not listed, every track opens unpatched.
  Fix: list every interface the template may run on, or patch once in LiveTrax, save, and
  read the device name from the saved session (`lt_dump.py`).

Connections between routes (track to Master) use `Connection other="<route>/<port>"`
and are written on both ends: on the track output port and on the Master input port.

## GUI state

`Extra/UI` holds windows named `RPM-<route id>` and `GUIObjectState` entries keyed by
route ids. After you rebuild the route list, remove them. LiveTrax rebuilds defaults.

## A common record layout (virtual soundcheck)

- Track N records `system:capture_N`.
- Track N's direct out goes to `system:playback_N`, back to the console as the virtual
  soundcheck source for channel N.
- Two-mix tracks (main mix, audience mics) have no direct out and feed Master.

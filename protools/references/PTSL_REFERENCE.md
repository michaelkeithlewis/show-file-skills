# PTSL reference (py-ptsl 601+, Pro Tools 2025.6.1 / PTSL 2025)

The surface of the `ptsl.engine.Engine` object, plus the gotchas found by
introspecting a live install. Signatures were captured on Pro Tools 2025.6.1.
Some recipes were also run on a later 2026 build; those are marked.

## Connecting

```python
import sys; sys.path.insert(0, "scripts")   # path to this skill's scripts/ folder
from ptctl import engine                    # convenience context manager
with engine() as e:
    ...
```

Or directly:

```python
from ptsl import open_engine
with open_engine(company_name="ShowFileSkills", application_name="ClaudeCode") as e:
    ...
```

The two strings are what Pro Tools shows in its "allow connection" dialog the
first time a client connects. Keep them stable so the grant sticks.

**Gotcha:** `open_engine(...)` returns a *context manager*, not the engine. Use it
in a `with` block (or call `.__enter__()`). Do not call `.close()` on the return
value of `open_engine`.

**Gotcha:** use the registered `engine()`. A raw gRPC probe that skips
`RegisterConnection` hangs, and looks like Pro Tools is wedged when it is not.

## Method catalog (grouped)

### Session info (read)
`session_name`, `session_path`, `session_sample_rate`, `session_bit_depth`,
`session_audio_format`, `session_timecode_rate`, `session_length`,
`session_start_time`, `session_interleaved_state`, `session_audio_rate_pull`,
`session_video_rate_pull`, `session_feet_frames_rate`, `ptsl_version`,
`get_session_ids`, `get_file_location`, `get_system_delay`,
`get_monitor_output_path`, `host_ready_check`.

### Session settings (write)
`set_session_audio_format`, `set_session_bit_depth`, `set_session_length`,
`set_session_start_time`, `set_session_time_code_rate`,
`set_session_interleaved_state`, `set_session_audio_rate_pull`,
`set_session_video_rate_pull`, `set_session_feet_frames_rate`.

### Session lifecycle (confirm before use)
`create_session`, `create_session_from_template`, `create_session_from_aaf`,
`open_session`, `save_session`, `save_session_as`, `close_session`,
`export_session_as_text`.

### Transport
- `transport_state() -> str`: returns `TS_Transport*` (Stopped, Playing,
  Recording, IsCued, FastForward, Rewind, ...).
- `toggle_play_state()`: start/stop playback (no args). `ptctl.py play`/`stop`
  wrap this with state awareness.
- `toggle_record_enable()`, `transport_armed()`, `record_mode()`,
  `set_record_mode(...)`, `playback_modes() -> (bool,bool,bool)`,
  `set_playback_mode(PlaybackMode)`, `play_half_speed()`, `record_half_speed()`.

### Tracks: query
- `track_list(filters=[]) -> List[Track]`: see the Track shape below.
- `select_tracks_by_name(names: List[str], mode=SelectionMode)`,
  `select_all_clips_on_track`, `extend_selection_to_target_tracks`.

### Tracks: state setters (all take `(track_names: List[str], new_state: bool)`)
`set_track_mute_state`, `set_track_solo_state`, `set_track_record_enable_state`,
`set_track_record_safe_enable_state`, `set_track_solo_safe_state`,
`set_track_input_monitor_state`, `set_track_inactive_state`,
`set_track_hidden_state`, `set_track_online_state`, `set_track_frozen_state`,
`set_track_open_state`. Also `set_track_dsp_mode_safe_state` and
`set_track_smart_dsp_state` (check arity before use).

### Tracks: create / rename / delete / color
- `create_new_tracks(number_of_tracks=None, track_name=None, track_format=None,
  track_type=None, track_timebase=None)`
- Raw form, for creating inside a folder:
  `CId_CreateNewTracks {number_of_tracks, track_name, track_type:"TType_Audio",
  track_format:"TFormat_Mono", track_timebase:"TTimebase_Samples",
  insertion_point_position:"TIPoint_Last", insertion_point_track_name:<folder>}`.
  `track_type:"TType_RoutingFolder"` makes a new routing folder.
- `rename_target_track(old_name, new_name)`.
- `CId_DeleteTracks {track_names}`: matches EVERY track with that name. Rename a
  loose source first if a template track shares its name.
- `CId_SetTrackColor {track_names, color_index}`: palette index only (1 to 69,
  or -1 no color / -2 default). Get the palette with
  `CId_GetColorPalette {color_palette_target:"CPTarget_Tracks"}`; it returns hex
  strings, index = position + 1. No arbitrary RGB, no white.

### Timeline / edit selection
- `get_timeline_selection(format=TimelineLocationType) -> (in, out)`
- `set_timeline_selection(in_time, play_start_marker_time=None, out_time=None,
  pre_roll_start_time=None, post_roll_stop_time=None, ...)`
- `get_edit_selection`, `get_edit_mode`, `set_edit_mode`, `get_edit_tool`,
  `set_edit_tool`, `get_main_counter_format`, `set_main_counter_format`,
  `get_sub_counter_format`, `set_sub_counter_format`.

### Memory locations / markers
- `get_memory_locations() -> List[MemoryLocation]` (fields: `.number`, `.name`,
  `.start_time`, ...)
- `create_memory_location(start_time=None, memory_number=None, name=None,
  end_time=None, location=None, reference=None, track_name=None, comments=None,
  color_index=None, ...)`
- `select_memory_location(mem_loc_id: int)`, `edit_memory_location`,
  `clear_all_memory_locations`, `get_memory_locations_manage_mode`,
  `set_memory_locations_manage_mode`.
- Remove specific markers: `CId_ClearMemoryLocation {location_list:[numbers]}`.

**Marker gotchas:**
- Unnumbered markers do not auto-increment: every one lands on the same slot.
  Pass an explicit free `memory_number` (`ptprep.place_markers` does this).
- Pass `reference=pt.MemoryLocationReference.MLReference_Absolute` so markers
  stay on their sample when you set the tempo later. Bar|Beat markers move.
- `color_index` on markers uses a separate 16-color marker palette.

### Clip editing
`cut`, `copy`, `paste`, `clear`, `trim_to_selection`, `duplicate_selection`,
`repeat_selection`, `consolidate_clip`, `group_clips`, `ungroup_clips`,
`regroup_clips`, `ungroup_all_clips`, `rename_target_clip`,
`rename_selected_clip`, `create_batch_fades`, `recall_zoom_preset`.

**Placing a clip on a track by id (the reliable way):**
```python
cl = e.client.run_command(pt.CommandId.CId_GetClipList,
                          {"pagination_request": {"limit": 800, "offset": 0}})
# rows have clip_id, clip_full_name ("Kick.L"), clip_root_name, clip_type, ...
e.client.run_command(pt.CommandId.CId_SpotClipsByID, {
    "src_clips": [left_id, right_id],          # list of clip-id UUIDs, not names
    "dst_track_name": "OH",
    "dst_location_data": {"location_type": "SLType_Start",
                          "location": {"time_type": "TLType_Samples", "location": "0"}}})
```
- Use the structured `location` sub-field. The legacy
  `location_value`/`location_options` pair raised `PT_UnknownError` (2026 build).
- A stereo file imports as two clips, `<name>.L` and `<name>.R`. Spot both ids
  together onto a stereo track. Spot one of them onto a mono track to turn a
  dual-mono file into a true mono track with no rebounce.
- Paginate the clip list on big sessions (64 stereo stems = 128 clips).
- Foldering or renaming strips a trailing space from a filename, so match clip
  root names to track names with `.strip()`.

### Undo
`undo`, `redo`, `undoall`, `redoall`, `clear_undo_queue`.

### Import / export / audio files (the disk-writing ones need confirmation)
- `import_audio(...)` (BROKEN, see below), `import_data`.
- `export_mix(base_name, file_type, sources, audio_info, video_info,
  location_info, dolby_atmos_info, offline_bounce)`: the bounce. See below.
- `export_clips_as_files`, `refresh_all_modified_audio_files`,
  `refresh_target_audio_files`.
- `CId_ExportSessionInfoAsText {include_track_edls:True, output_type:"ESI_String"}`:
  the session as text, with one EDL row per clip under each `TRACK NAME:`.
  This is the only trustworthy check that a clip landed on a track.

## The `Track` object

Fields: `name`, `type`, `id`, `index`, `color`, `format`, `timebase`,
`parent_folder_name`, `parent_folder_id`, `track_attributes`.

`type` is a `TrackType` enum (`TType_Audio`, `TType_Aux`, `TType_Vca`,
`TType_RoutingFolder`, `TType_BasicFolder`, `TType_Master`, `TType_Midi`,
`TType_Instrument`, ...). `format` is `TrackFormat` (`TFormat_Mono`,
`TFormat_Stereo`, `TFormat_5_1`, ...).

`ptctl.py tracks` prints a summary without `parent_folder_name`. Read the live
objects when you need the folder:
`ptctl.py exec "import json;print(json.dumps([(t.name,t.parent_folder_name) for t in e.track_list()]))"`.

### `track_attributes`: two field kinds

**Plain bool** (true/false directly): `is_muted`, `is_soloed`,
`is_record_enabled`, `is_record_enabled_safe`, `is_soloed_safe`, `is_frozen`,
`is_locked`, `is_open`, `is_online`, `contains_clips`, `contains_automation`,
`is_smart_dsp_on`, `is_smart_dsp_on_safe`.

**`TrackAttributeState` enum** (`is_inactive`, `is_hidden`, `is_selected`,
`is_input_monitoring_on`, `has_edit_selection`): values are
`0 Unknown, 1 None, 2 SetExplicitly, 3 SetImplicitly, 4 SetExplicitlyAndImplicitly`.
**The attribute is "on" only when the value is 2 or more.** `1` means not set.
`ptctl.py`'s `_attr_set()` handles this; do not treat these as plain bools.

`track_list()` does not reliably fill every attribute (for example online state)
unless you request it with filters, so a missing flag is not proof it is off.

## Display enums (int to name)

- `pt.BitDepth`: 2=16, 3=24, 4=32Float
- `pt.SampleRate`: 44100/48000/88200/96000/176400/192000
- `pt.SessionAudioFormat`: 1=WAVE, 2=AIFF
- `pt.SessionTimeCodeRate`: 1=23.976 ... 4=29.97 ... 6=30 fps (see `STCRate_*`)
- `pt.TrackType`, `pt.TrackFormat`: see above.

Resolve with `pt.<Enum>.Name(value)` where `from ptsl import PTSL_pb2 as pt`.

## Bouncing a mix (`export_mix`)

`export_mix` bounces **the current timeline selection**. Recall a selection memory
location first (`ptctl.py locate <n>`) or set the selection. Working recipe
(2026 build):

```python
from ptsl import PTSL_pb2 as pt
ai  = pt.EM_AudioInfo(compression_type=pt.CT_PCM, export_format=pt.EF_Interleaved,
        bit_depth=pt.Bit24, sample_rate=pt.SR_48000,
        pad_to_frame_boundary=pt.TB_False, delivery_format=pt.EM_DF_SingleFile)
loc = pt.EM_LocationInfo(import_after_bounce=pt.TB_False,
        file_destination=pt.EM_FD_SessionFolder)          # see gotcha below
src = [pt.EM_SourceInfo(source_type=pt.EMSType_Bus, name='PrMst')]
e.export_mix(base_name='Song Title_V1', file_type=pt.EMFType_WAV, sources=src,
    audio_info=ai, video_info=pt.EM_VideoInfo(), location_info=loc,
    dolby_atmos_info=pt.EM_DolbyAtmosInfo(), offline_bounce=pt.TB_True)
```

It is **synchronous**: when `export_mix` returns, the file is written (a 4-minute
offline bounce took about 110 s). The file lands in the session's `Bounced Files/`.

**Find the valid `sources` name.** Do not guess. A bad name raises ErrType 100
"None of the specified mix sources are present and in use":
```python
e.client.run_command(pt.CommandId.CId_GetExportMixSourceList, {'type': 'EMSType_Bus'})
# also: EMSType_PhysicalOut / EMSType_Output / EMSType_Renderer
```
It returns `{'source_list': [...]}`, and lists only buses that something already
feeds. `get_monitor_output_path()` returns the monitor path, which is NOT the
bounce source.

**Gotchas:**
- **`EM_FD_Directory` with a custom directory raised an assertion**
  (`Sys_FileLocMacOS.cpp`, ErrType 100). Use `EM_FD_SessionFolder` and move the
  file afterwards.
- **No fader/gain command exists** in PTSL. To bounce at unity, set the master
  fader by hand.
- `CId_GetTrackControlInfo` / `CId_GetTrackControlBreakpoints` exist for reading
  control values and automation, but they are Private API (see below).

Pick one naming pattern for bounces and keep it, for example
`<Song>_<Initials>_V<n>_PtMst.wav` (`PtMst` = post master bus, `PrMst` = pre master bus).
Pass that string (minus `.wav`) as `base_name`, and use the same string as the file
name when you deliver it. To find the next version number, list `Bounced Files/`.
The full naming, versioning and delivery convention is in `session-prep.md`
("Bounce, name, version, deliver"); uploading to Samply is in `../../samply/`.

To bounce several buses in one pass (one file per bus), pass every bus as a source
and set `EM_DF_FilePerMixSource`. With `SingleFile` and several sources, Pro Tools
writes one multichannel file instead.

## Create a session from scratch + import audio (2026 build)

```python
b = e.create_session("My Session", "/parent/dir")   # location = PARENT dir;
b.wave_format(); b.sample_rate(48000); b.bit_depth(24)   # PT makes <parent>/<name>/<name>.ptx
b.create()
```
- Save the open session first, so the close-on-create cannot hang on a
  "save changes?" dialog.
- If `~/Documents` is iCloud-synced, create into a `.nosync` folder (see
  `session-prep.md`).

**`Engine.import_audio()` IS BROKEN.** It hardcodes `import_type=1`, which is
`Session` import, not `Audio`, so every call fails with
`ErrType 11 OS_NoFilePathFound (The path to the imported session is missed.)`.
Call the command directly:

```python
req = {'import_type':'IType_Audio', 'audio_data':{
  'file_list':[...absolute paths...],
  'audio_operations':'AOperations_AddAudio',   # by reference; ConvertAudio = SRC copy
  'audio_destination':'MDestination_NewTrack', # or MDestination_ClipList
  'audio_location':'MLocation_SessionStart',
  'location_data':{'location_type':'SLType_Start','location_options':'TOOptions_TimeCode',
                   'location_value':'00:00:00:00'}}}
e.client.run_command(pt.CommandId.CId_Import, req)
```
- `AddAudio` imports by reference, so the session's `Audio Files` folder stays
  empty. If the source folder moves or is evicted, the session loses its audio.
- `ConvertAudio` / `CopyAudio` need `destination_path` (the session's `Audio Files`
  folder), or they fail with the same path error. `ConvertAudio` sample-rate
  converts to the session rate (about 10 s per 16-minute 96k mono file).
- Each file lands on a new track named after the file. An imported `X L` + `X R`
  mono pair may be combined into one stereo track named `X`.

## Private API and output routing

`CId_SetTrackMainOutputAssignments` is public but needs a `signalpath_id`.
The original tests could not retrieve one through `CId_GetTrackControlInfo`
without the Private API / an Avid-issued encrypted key (`CId_EnableAPI`).

**Newer tested path:** with Pro Tools 2026.4.1 and SDK 2026.4 bindings,
`CId_GetTrackMainOutputAssignments` returned `signalpath_ids` for an already
routed track, and the setter assigned those IDs to other tracks. No EnableAPI
call or private key was supplied by those test scripts. This is assigned-route
reuse, not bus-name enumeration or new-bus creation. See the exact scope and
request shapes in [macOS session-prep field notes](macos-session-prep-field-notes.md).
Keep Accessibility (`ptax.py`, `route_folders.py`) for unsupported versions,
seeding the route by name and remaining GUI gaps.

There is also no PTSL command for: tempo or meter, pan, fader or volume, plug-in
insert or bypass, track reorder, moving a track into a folder, split-to-mono, or
combine-to-stereo.

## Field notes: revisions and markers

- **Memory locations:** `CId_CreateMemoryLocation` takes `number` (not `memory_number`; a wrong
  field fails silently). `start_time` and `end_time` must share a reference type: copy Bars|Beats
  strings from existing markers and pass `reference: "MLR_BarBeat"`, or pass samples with
  `"MLR_Absolute"`.
- **Fades:** `CId_CreateFadesBasedOnPreset` with "Only New Fades" plus `auto_adjust_bounds` turns
  a gap into a crossfade. For a real gap, use "Only Fade Outs" or "Only Fade Ins" with
  `auto_adjust_bounds: false` on a selection that ends or starts at the gap.
- **Range clip gain:** `ptgui.nudge_clip_gain_range(e, track, t0, t1, steps)` selects the track,
  sets the timeline selection and nudges. Pro Tools puts the clip-gain breakpoints at the
  selection edges, so put the edges where the audio is quiet or masked. On one test, a 39 s
  range measured exactly -4.0 dB inside, with no clicks at the edges.
- **Check a fix with a bounce from the song start, never a short range.** Time-based and
  triggered plug-ins (motion panners, auto-panners, LFOs) carry state from where playback
  starts. A retrigger pop from a motion panner did not appear in a 5-second bounce, but it did
  in the full bounce.
- **A silent gap does not stop a triggered plug-in.** A 10 ms hole moved the pop 26 ms later,
  to just after the audio came back. A 3 ms AR interpolation on the bounced file
  (`declick.py`) hides it; the real fix is automation or a bypass for that moment.
- **Find a pop by bus, then by sample.** Bounce every bus in one `EM_DF_FilePerMixSource` pass.
  The bus with the HF burst names the folder. A one-sample step in that bus, with smooth raw
  stems under it, means automation or a plug-in did it. The stem whose raw value matches the
  size of the step is the source. When a pop shows on a folder bus over smooth stems, check
  that folder's motion and auto-pan plug-ins first.

## Discovering anything else

```python
import inspect
from ptsl.engine import Engine
print(inspect.signature(Engine.<method>))      # exact args for any method
from ptsl import PTSL_pb2 as pt
print([n for n in dir(pt) if 'Foo' in n])       # find enums / message types
```

`ptctl.py caps` probes the version-gated commands on your build and diffs the
command list against `ptsl_commands_baseline.json` (the Pro Tools 2025.6 list), so
new commands show up after a Pro Tools update. Run `pip install -U py-ptsl` first.

# LiveProfessor 2 session (.rack2) format notes

Decoded by hand from sessions saved by LiveProfessor 2.
Audiostrom does not publish this format.

## Container: JUCE binary ValueTree

A `.rack2` file is one JUCE `ValueTree` written with `ValueTree::writeToStream`.
There is no header, no compression and no checksum. `vt.py` reads and writes it and
round-trips every sample byte for byte.

Node:

```
type name, UTF-8, NUL-terminated
compressed int: property count
  property name, NUL-terminated
  var (below)
compressed int: child count
  child nodes
```

Compressed int: one byte `n` (low 7 bits = byte count, bit 7 = negative), then `n`
bytes of little-endian magnitude. Zero is the single byte `00`.

var: a compressed-int size, then `size` bytes. The first byte is the type tag:

| Tag | Type | Payload |
|---|---|---|
| 1 | int | int32 LE |
| 2 | bool true | none |
| 3 | bool false | none |
| 4 | double | float64 LE |
| 5 | string | UTF-8 + NUL |
| 6 | int64 | int64 LE |
| 7 | array | compressed-int count, then vars |
| 8 | binary | raw bytes |
| 9 | undefined | none |

Size 0 means a void var.

Keep the original type when you change a value. Ids are often int64 in one place and
int in another, and LiveProfessor compares them by value.

## Root: `LiveProfessorProjectFile`

Props: `isTemplate`, `ProjectFileVersion`, `appVersion`, `description`, `fixGainBug`.
Children seen:

| Node | Holds |
|---|---|
| `AudioMidiHardware` | `IOdeviceProperties` (device type, input/output device name, active channel bit masks, `RequiredInputs`/`RequiredOutputs`), `AudioInputs`/`AudioOutputs` (one child per channel: `Index`, `UserLabel`), `MidiDevices` |
| `projectSettings` | `BufferSize`, `AutoSaveCounter`, `useSIPmode` |
| `Chains` | the chains (below) |
| `WindowManager` | view sets |
| `TempoAndSync` | tempo, MIDI clock |
| `GlobalSnapshots` | song snapshots (`GlobalSnapshot` children), `ActiveSnapshot`, `GlobalSnapshotFilter`, `GlobalSnapshotTriggers` |
| `GlobalSnapshot` | the current state (below) |
| `CueLists` | cue lists (`CueName`, `CueNumber`, `CueUid`, ...), OSC destinations |
| `GlobalOscController`, `HardwareControllers` | remote control |
| `uiComp` | UI component tree |
| `WireView/Nodes` | `WireViewNode` per node: `NodeId`, `XPos`, `YPos` |

Not every file has every node. One sample had `AudioOutputs` and no `AudioInputs`.

## Chains

```
Chain  ChainViewOrder
  ChainSettings  ChainColour (ARGB hex string, "ffRRGGBB"), DelayMode, ManualDelayMs,
                 ChainInputCount, ChainOutputCount, ChainMainInputBusConfig ("C" or "L R"),
                 ChainMainOutputBusConfig, SideChainCount, AuxCount, ...
    ProcessorSettingsContainer  name, id     <- the chain's node id
      processorState  enabled, bypassed, isolate, audioMute, inputGain, outputGain
      midi
    ProcessorOrder
      plug  id (= pluginUid), type ("VST3-<Name>-<hex>-<hex>", "AU-...")
  ChainPlugins
    Plugin  pluginTypeId, pluginTypeName, pluginUid
      ProcessorSettingsContainer  name, id (= pluginUid)
      Plugin  (plugin state, PluginSnapshot children with uId, updateTime)
      bussesLayout
  ChainSnapshotList
```

`DelayMode` values seen: 0 and 1. The exact meaning was not confirmed in the UI.

## Node ids and routing

- Node 1 = hardware inputs. Node 2 = hardware outputs.
- A chain's node id = its `ProcessorSettingsContainer` id.
- Channel ids are 0-based. Channel id 4096 and up are MIDI ports.

Routing lives in the top-level `GlobalSnapshot`, in `AudioPatch` and `MidiPatch`:

```
AudioPatch
  outputs  nodeId, channelId           <- one per source channel
    point  outputNodeId, outputChannelId, inputNodeId, inputChannelId, isMidi
```

Each song snapshot under `GlobalSnapshots` carries its own copy of the patch. If you
rebuild the routing and keep the song snapshots, recalling one brings back the old
routing. `lp_generate.py` removes them.

## The current state repeats the chains

The top-level `GlobalSnapshot` holds `Workspace`, `MidiPatch`, `AudioPatch`,
`TempoAndSync`, `Chains`, `Plugins`, `GlobalSnapshotFilter`. Its `Chains` and `Plugins`
are a second copy of the root `Chains` list, derived exactly:

- `GlobalSnapshot/Chains/Chain` = prop `ChainId` (int64, the chain id) + the
  `ChainSettings` props + copies of the `ChainSettings` children.
- `GlobalSnapshot/Plugins/Plugin` = prop `PluginId` (int64, the pluginUid) + copies of
  the plugin's children, without `bussesLayout`. Each `PluginSnapshot` has its own
  `uId` and `updateTime`.

`check_derive.py` tests this rule on any saved session. It held on every sample.

## Other references to chains and plugins

- `GlobalSnapshotFilter/SnapshotFilter/PluginFilter` has one bool prop per chain id and
  plugin id. The prop name is the id as a decimal string.
- `storedViewSetItems` (plugin windows) reference `storedViewSetItemPluginId`.
- `WireView/Nodes` has one `WireViewNode` per chain.

After you remove a chain or plugin, no int property and no decimal-string prop name may
still hold its id. `lp_generate.py` checks this before it writes.

## Opening a generated file

On macOS, `open -a LiveProfessor file.rack2` started the app but did not load the
project in testing. Open the file from inside LiveProfessor. A file generated this way
opened in LiveProfessor 2 and worked.

# macOS session-prep field notes: Pro Tools 2026.4.1

Contributed by Franklin Rice from local disposable-session tests completed on
2026-10-23. These findings supplement the existing playbook; they do not replace
its scripts, template preferences or results from other versions.

## Tested environment and scope

- Pro Tools 2026.4.1 on macOS; generated Avid PTSL bindings from SDK 2026.4.
- Python 3.9.6, grpcio 1.80.0, protobuf 6.33.6.
- The local transport used request header `version=2025`, `version_minor=10`.
  That records the configuration that worked; it is not a recommendation to use
  these header values with every binding/server version.
- SDK operations used registered local connections. No EnableAPI call or
  Avid-issued private-API key was supplied by the test scripts.
- The pipeline combined PTSL, AppleScript/JXA and native macOS Accessibility.
  It drove a running Pro Tools instance; it did not write the PTX binary format.

## Reuse an assigned output identifier through the SDK

The existing notes describe GetTrackControlInfo as the only way to retrieve an
output identifier. In this newer binding/server combination,
`CId_GetTrackMainOutputAssignments` returned `signalpath_ids` for an already
routed track. Those IDs were accepted by `CId_SetTrackMainOutputAssignments` for
other tracks. We first proved an actual destination change between two test
tracks, then used the same method for grouped category-folder outputs.

The following is transport-neutral pseudocode. `call` means a registered SDK
request with task-status/error checks, not a function added by this contribution:

```python
# Establish the intended route on one seed track through the UI if necessary.
assigned = call("GetTrackMainOutputAssignments", {"track_ids": [seed_track_id]})
ids = assigned["signalpath_ids"]
assert len(ids) == 1  # tested case: one stereo main output
call("SetTrackMainOutputAssignments", {
    "track_ids": destination_track_ids,
    "signalpath_ids": ids,
})
```

Read the assignments back and verify actual output names against the intended
bus. A successful re-assignment to the current route alone does not prove that
changing destinations works. Preserve session-path guards and confirm that all
targets are in the current session. Do not store IDs as portable bus presets or
guess IDs from bus names, track IDs or a numeric sequence.

This is **not bus-name enumeration**, new-bus creation or folder-input assignment.
Accessibility is still useful for seeding the first output by name and setting
folder inputs. The tested CreateSignalPath bus-creation request still returned
an unsupported-operation result. Check binding/server support before expecting
the newer getter; earlier private-API failures remain valid observations for
the requests/versions tested there.

## Session-data import: a request that completed

A blanket claim that IType_Session always fails headlessly does not hold for
this configuration. The following request completed against a prepared template
copy containing exactly the intended processing/effects/master section:

```python
call("Import", {
    "session_path": prepared_template_path,
    "import_type": "IType_Session",
    "session_data": {
        "audio_options": "AMOptions_CopyFromSourceAudio",
        "audio_handle_size": 1000,
        "video_options": "VMOptions_LinkToSourceVideo",
        "match_options": "MTOptions_ImportAsNewTrack",
        "playlist_options": "MPOptions_DoNotImport",
        "track_data_to_import": {
            "clips_and_media": False,
            "clip_gain": False,
            "volume_automation": True,
        },
        "timecode_mapping_units": "TCMOptions_MaintainAbsoluteTimeCodeValues",
        "timecode_mapping_start_time": "00:00:00:00",
        "adjust_session_start_time_to_match_source": False,
    },
})
```

The explicit nonzero audio_handle_size was present in successful requests.
This was not a controlled single-field experiment, so it does not establish
that the field alone caused success or that the number is universally required.

Deselect all tracks/folders before importing. Compare the resulting added
track names/types/formats against the prepared template inventory, preserve
all pre-existing track identities/controls, and compare clips, file references
and tempo/meter rulers before and after. In our workflow imported automation
was then cleared over a selection longer than the song. Main Playlist was Do
Not Import; source clips/media were not brought in. The template profile was
explicit, not an arbitrary track selection inferred from a giant import table.

## Folder-derived routing and ordered imports

The macOS Move to New Folder flow created the intended routing bus and assigned
member outputs when the folder was named **before Create**, Routing Folder was
selected and Route Tracks to New Folder was enabled. Verify both membership and
the actual folder input/member outputs; hierarchy alone is not audio routing.
If Basic Folder is displayed, selecting that control then Up/Return worked in
the tested UI; if Routing Folder is already displayed, omit that sequence.
Focus the actual modal before typing and stop on an unresolved modal.

Importing each drum source in the desired order avoided a later reorder. Some
mono L/R source pairs were imported separately to avoid Pro Tools combining
them into one stereo track. These are implementation choices, not changes to
the maintainer's preferred taxonomy or folder format.

## Accessibility observations

- An AX action can report an error after successfully opening a modal. Inspect
  the resulting dialog/value before retrying; do not double-submit a mutation.
- The system-wide AX focused-application PID gave a fresh foreground check where
  NSWorkspace foreground state was stale in the command-line helper.
- The tested numeric entry controls accepted only the first character of one
  multi-character Unicode event. Sending one character per event and verifying
  the value before OK worked for both Tempo Change and Meter Change at bar one.
- Ignore only the recognized single-child macOS sharing-decoration window;
  do not treat an arbitrary unnamed dialog as safe to dismiss.
- Launch the serialized UI worker before connecting the gRPC client. This order
  worked in our runner; no causal claim is made that all other orders fail.

## Optional MonoMate handoff findings

For workflows that already use MonoMate:

1. Check the exact source folder, preferences, scan completion and file count.
2. The Convert control can be temporarily absent during loading. Poll its
   enabled state once available; pending checks used a one-second cadence when
   query time permitted. Long AX traversals can exceed that interval.
3. SwiftUI exposed all row objects but only visible cell text. Requiring every
   offscreen filename caused a false timeout. Validate complete inventory from
   row counts and then reconcile the actual files.
4. Reuse live control references and combine checks into one traversal. Repeated
   full-tree reads and a synchronous selection action caused a measured four-
   second post-readiness delay in an earlier version.
5. Post Select All Convertible once and Convert once, then wait for a recognized
   completion summary. Native clicks used live AX control geometry, not stored
   screen coordinates. Do not blindly click Convert every second.
6. MonoMate gathered originals from nested categories into one delivery-root
   backup folder. Match unique basenames and verify original CRCs against the
   delivery ZIP. Check output frame counts, sample rates and bit depths too.

Two refined isolated tests took 28.54 and 29.34 seconds for the complete helper,
with 38 originals verified, 16 conversions and 16 backups each. The final full
run's helper took 21.24 seconds. The Convert click was queued within 0.01 seconds
**after all readiness checks passed**, not necessarily within that interval of
the UI first becoming enabled. These timings vary with app/cache state.

The experimental fast helper still required a positive conversion count. A
zero-conversion delivery needs a separate bypass/test. These notes do not add
MonoMate as a mandatory dependency of the existing repository.

## Checkpoints and failure handling

Keep original deliveries and run records separate from generated media. The
local runner recorded job fingerprints, before/after inventory and pending
phases around imports/folder creation. A timeout or BadResponse can be an
uncertain mutation: reconcile the actual session before repeating it. Inspect
non-warning response errors as well as transport/task completion.

A PACE/iLok authorization failure interrupted an earlier test before audio
import. A recovery copy preserved the session; the later success does not prove
that licensing failure can never recur. Do not suppress an authorization error
and continue. Test runs were local; automated Dropbox offline pinning was not
exercised.

## Sanitized full-run result

One uninterrupted local run, with no retries or manual UI intervention:

| Stage | Seconds |
|---|---:|
| ZIP extraction / client-song hierarchy | 7.039 |
| MonoMate helper | 21.242 |
| SDK session creation | 1.161 |
| Tempo / meter UI helper | 3.842 |
| Source import / folders / colors / panning / checks | 53.805 |
| Prepared-template import / final routing / automation clear / save | 28.324 |
| Other startup / coordination / prior test close | 3.666 |
| **Prep total, excluding Finder tagging** | **119.079** |

The previous completed full run took 188.360 seconds. This is a measured 36.8%
reduction for one known delivery/template on one Mac, not a general benchmark.

Inventory: 38 active sources, 16 conversions with retained originals, 12 category
folders, 38 added template tracks and 88 total tracks. All 38 media references
were online inside the new session's Audio Files directory. The session was
48 kHz / 24-bit, 76 BPM, 6/8; final folders were closed, tracks deselected,
automation cleared and the session saved. One unmatched mono R label was left
unchanged and flagged for engineer review.

Rough wall-time attribution was 33.15 seconds in extraction/bulk processing wait
windows and 85.93 seconds in control, UI reads and checks. Calls mix app work,
IPC and waiting; this was not CPU profiling or active AI reasoning time.
Remaining overhead included 146 GetTrackList calls, 65 GetSessionPath calls,
61 modal-readiness checks and 50 routing reads. Grouping IO checks/reusing
validated state within categories is a next experiment; these calls are not
all redundant, so their total is not a promised saving.

No client audio, PTX templates, private paths, credentials or runtime journals
are included here. Source bindings remain separately obtained from Avid.
Requested trigger-track duplication, additional clip-gain targeting and audio-
content identification were not implemented or proved by this local test;
that does not negate separate existing implementations in this repository.

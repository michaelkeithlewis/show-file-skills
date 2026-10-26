---
name: samply
description: Deliver audio through Samply (samply.app), the audio sharing platform for live music, touring and post-production - list projects and folders, create folders, upload a mix or rehearsal, add a new mix as a version of an existing song, rename without re-uploading, and combine two mono files into one interleaved L/R stereo WAV (the lighting and video pattern, SMPTE timecode on one side and program audio on the other). Trigger on "Samply", "samply.app", "post to Samply", "upload to Samply", "Samply folder", "send the mix to the client", "upload V2", "for lighting" in an audio context, "interleave L/R", "make a stereo file", or "merge these two mono files", especially with SMPTE, timecode, click, FOH mixes, playback stems, or rehearsal and show audio. NOT for Dropbox, Google Drive or WeTransfer, and not for audio editing beyond channel packing.
---

# Samply: audio delivery and L/R interleaving

Two jobs that often come together:

1. **L/R interleave:** combine two mono files into one interleaved stereo WAV with
   FFmpeg. The classic case is SMPTE timecode on L and program audio (FOH mix, click,
   stems) on R, for a lighting console or a video playback rig.
2. **Upload to Samply:** push that file (or any mix) into a project or folder through
   the Samply REST API, as a new track or as a new version of an existing one.

## Credentials

The API uses a bearer token. `scripts/samply_cli.py` reads it from, in order:
`$SAMPLY_API_TOKEN`, the file named by `$SAMPLY_TOKEN_FILE`, then
`~/.config/samply/token`. Setup is in README.md. Never print the token, and redact it
from any command output you show. If no token is found, ask the user for one; do not
search the machine for it.

## API essentials

- Base URL: `https://samply.app/api/v0`. Header: `Authorization: Bearer <token>`.
- `GET /projects`: projects with `id`, `name`.
- `GET /projects/:pid/folders`: folders with `id`, `name`, `children`.
- `POST /projects/:pid/folders {"name", "parentid"?}`: create a folder (nested with `parentid`).
- `POST /projects {"name"}`: create a project. The API ignores `color`.
- `GET /projects/:pid/files/:stackid`: a stack with its real `name` and a `children`
  array of version boxes (`v1`, `v2`, ...). Folder `children` give bare stack ids only,
  so resolve names one stack at a time.
- `POST /projects/:pid/files/:id {"name"}`: rename a stack or a version. No re-upload.
- Upload: two-step signed URL (below).

### What the API cannot do

- **No move and no delete** through the API (PATCH, PUT, DELETE and `/move` paths 404 on
  folders and projects). Reorganizing an account is drag-and-drop in the web app. Build
  the destination projects and folders with `POST`, hand the user an explicit
  source-to-destination map, and say the moves are manual.
- **No download.** The download route answers 200 with an empty body.
- **Root files are not listable.** `/folders` returns folders only.
- **No access setting.** A new project may be invite-only; set "Anyone with the link"
  in the web app's Share panel if the user wants a link anyone can open.
- **No version order or labels.** Stacking a reference under a mix, reordering versions,
  and labels such as `demo` are done in the web app.
- Anything you create with `POST` stays until someone deletes it by hand. Never create
  scratch or test projects in a live account.

## Workflow

### 1. Find the project and folder

```bash
python3 scripts/samply_cli.py list-projects
python3 scripts/samply_cli.py list-folders --project "<artist or show>"
```

Matching is case-insensitive, exact first, then substring. If several match or none
does, ask the user. Create a missing folder only when the request implies it
(`create-folder`).

### 2. Interleave (only when an L/R file was asked for)

Both sources must be mono, with the same sample rate and length. Probe first:

```bash
ffprobe -v error -show_entries stream=codec_name,sample_rate,channels,bits_per_raw_sample \
  -show_entries format=duration INPUT.flac
```

The FIRST input becomes LEFT, the second RIGHT. Confirm the assignment when context
does not make it obvious (SMPTE on L is the lighting convention).

```bash
scripts/interleave_lr.sh LEFT.flac RIGHT.flac OUTPUT.wav [pcm_s24le|pcm_s16le]
```

- `pcm_s24le` keeps 24-bit sources at 24-bit; use `pcm_s16le` for 16-bit sources.
- If the rates differ, resample one explicitly. Do not let FFmpeg pick.
- `join` gives an explicit L/R order; `amerge` can reorder channels.
- Stereo 24-bit 48 kHz is about 1 MB per second (a 75-minute rehearsal is about
  1.3 GB). Check free disk first.

### 3. Upload

```bash
python3 scripts/samply_cli.py upload --project "<project>" --folder "<folder>" \
  --file "/path/to/Song Title_AB_V1_PtMst.wav"
```

- Omit `--folder` to upload to the project root. Use `--folder-id` when folder names
  repeat (for example a `Full` folder under every song).
- **A new mix of a song that is already there is a new version, not a new track:**
  `--version-of <stack id>`. It lands on top of that stack as the newest version, and
  the stack shows its name. Uploading with the same name alone makes a duplicate track.
  Get the stack id from `list-folders` (folder children) or the song's web URL
  (`samply.app/project/<pid>/file/<stackid>`), and check it with `stack`.
- `--name` defaults to the file's basename. Name it right first time: a stack's display
  name is its newest version's name. Fix a name with `rename`, not a re-upload.

### 4. Verify in the web app, not only through the API

A 200 on the PUT and a stack that reads back through the API do not prove the file
processed. During one Samply outage, every upload that day returned 200 and read back
as a healthy stack, and every one sat forever with a spinner and no duration. Open the
project in the web app: a processed track shows a duration (`3:22`), a dead one a
spinner. A small file processes in under a minute; a multi-GB WAV takes longer. The
fix for a dead upload is to upload the same file again once Samply is healthy, then
trash the spinner copy in the web app.

`list-folders` is still a fine check that the stack landed in the right folder.

### Links

Share links look like `https://samply.app/p/<shareid>?token=<uuid>`, and a file link adds
`/file/<stackid>?version=<versionid>`. After an outage Samply has reset every link in an
account, so old links 404. Get the current link from the project's Share panel. A link
without its `token` 404s. An archived project shows "Access Denied" to the client;
restore it from the archive page.

## Upload flow (what the CLI does)

1. `POST /projects/:pid/files` with `{"name", "mimeType", "size", "parentid"?}` (`parentid`
   = a folder id, or a stack id for a new version). The response has `url` (a signed
   GCS URL, about 15 minutes), `boxid`, `stackid`, `contentType` and
   `metadata.{destination, projectid, boxpath}`. With a stack id, the empty version box
   exists from this moment, so do not POST just to look.
2. `PUT` the raw bytes to `url` with `Content-Type: <contentType>`,
   `x-goog-meta-destination`, `x-goog-meta-projectid` and `x-goog-meta-boxpath` set from
   step 1. The signature covers these headers.

Gotchas: do not set `Content-Length` by hand; do not use `curl --data-binary @file` for a
large file (it buffers it all in memory; use `curl -T` or the script); quote the signed
URL in a shell, it contains `&`.

## MIME types

| Extension | mimeType |
|---|---|
| .wav | audio/wav |
| .flac | audio/flac |
| .aif, .aiff | audio/aiff |
| .mp3 | audio/mpeg |
| .m4a | audio/mp4 |
| .ogg | audio/ogg |

Anything else: `mimetypes.guess_type`.

## Naming mixes

Use the same name as the bounce: one convention, everywhere. For example
`<Song>_<Initials>_V<n>_PtMst.wav` (Title Case song, mixer's initials, version, bus).
Do not use a project's track-number names (`06 - SONG.wav`) or `SONG V2`. Send the
client the `_PtMst` (post master bus) print, never the `_PrMst`. The full convention,
and how a Pro Tools bounce gets here, is in `../protools/references/session-prep.md`
("Bounce, name, version, deliver").

## Common patterns

- **"Push Thursday's run to <show> for lighting":** find the two mono files (timecode
  and the mix), interleave with SMPTE on L, upload to the lighting folder, verify.
- **"Upload this mix":** one file, no interleave. Ask for the project or folder if not given.
- **"Here's V2 of <song>":** upload with `--version-of` the song's stack.
- **"Make an L/R split from these stems":** interleave only. No upload unless asked.

## When not to use this

- Another destination (Dropbox, Google Drive, WeTransfer, Box).
- Mixing, stem separation, or editing beyond channel packing.
- A container other than WAV with no reason given. WAV is the safe format for
  lighting consoles and playback rigs. FLAC or AIFF is a codec swap (`-c:a flac`, or
  `-c:a pcm_s24be` into `.aif`).

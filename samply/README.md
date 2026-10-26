# samply: deliver audio through Samply from Claude Code

A Claude Code skill and a small CLI for [Samply](https://samply.app), the audio sharing
platform many touring and studio crews use to pass mixes, rehearsals and show audio
around. It uploads mixes into the right project and folder, adds a new mix as a new
version of a song instead of a duplicate, renames without re-uploading, and builds the
L/R stereo file that lighting and video rigs want (timecode on one side, audio on the
other).

You ask in plain words ("upload V2 of the song to the client's project", "push
Thursday's run to the lighting folder with timecode on the left") and Claude runs the
scripts in this folder.

## What it does

- **Upload:** resolve a project and folder by name, request a signed URL, stream the
  file (multi-GB WAVs are fine), print the stack id (`scripts/samply_cli.py upload`).
- **Versions:** `upload --version-of <stack id>` puts a new mix on top of the song's
  existing stack, so the client's link and comments stay on one track.
- **Housekeeping:** `list-projects`, `list-folders`, `create-folder`, `stack` (a song's
  versions), `rename`.
- **L/R interleave:** `scripts/interleave_lr.sh LEFT RIGHT OUT.wav` (FFmpeg `join`).
- **Notes:** `SKILL.md` lists what the Samply API cannot do (move, delete, download,
  access settings, version order) so Claude does not go looking for endpoints that are
  not there, and how to verify that an upload really processed.

It pairs with the [`protools/`](../protools/) skill in this repo: that one bounces
`<Song>_<Initials>_V<n>_PtMst.wav` into `Bounced Files/`, and this one delivers it.

## Requirements

- Python 3.8 or later with `requests` (`pip install requests`).
- FFmpeg and ffprobe for interleaving (`brew install ffmpeg`).
- A Samply account and an API token for it (see Samply's own API documentation for how
  to get one).

## Install

1. Copy this folder to `~/.claude/skills/samply`.
2. Give the CLI your token. Pick one:
   - an environment variable: `export SAMPLY_API_TOKEN=...` (in your shell profile, or
     from your password manager or keychain when the shell starts), or
   - a file only you can read:
     ```
     mkdir -p ~/.config/samply
     printf '%s\n' '<your token>' > ~/.config/samply/token
     chmod 600 ~/.config/samply/token
     ```
     or any other path, named by `SAMPLY_TOKEN_FILE`.

   Never commit the token or paste it into a chat. The CLI never prints it.
3. Check it: `python3 ~/.claude/skills/samply/scripts/samply_cli.py list-projects`.

## Quick start

```
CLI="python3 scripts/samply_cli.py"
$CLI list-projects
$CLI list-folders --project "<project>"
$CLI upload --project "<project>" --folder "Mixes" --file "Song Title_AB_V1_PtMst.wav"
$CLI upload --project "<project>" --version-of <stack id> --file "Song Title_AB_V2_PtMst.wav"
$CLI stack  --project "<project>" --stack-id <stack id>
$CLI rename --project "<project>" --file-id <id> --name "Song Title_AB_V2_PtMst.wav"
scripts/interleave_lr.sh smpte.wav foh.wav "Run - For Lighting.wav"
```

## Status

- Proven in daily use: `list-projects`, `list-folders`, `create-folder`, `upload` to a
  folder and to a project root, and multi-GB uploads. The rename call and adding a
  version through `parentid` were proven as direct API calls.
- New in this release and not yet run against the live API: the `stack` and `rename`
  subcommands and the `--version-of` flag as CLI options (each wraps an API call listed
  above that was used directly before).
- Verified for this release: `python3 -m py_compile` and `--help` on the CLI,
  `bash -n` on the interleave script.

This project is not affiliated with or endorsed by Samply. No warranty.

## Built on tour

Built by Michael Lewis, a touring engineer and co-founder of [Truck Packer](https://truckpacker.com), the truck-pack planning app for touring and production crews.

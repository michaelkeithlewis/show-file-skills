#!/bin/bash
# push_session_data.sh <source.ptx> <target.ptx> [<target.ptx>...]
#
# Copies a mix-template change from one session into others through File > Import >
# Session Data, driven by Accessibility (no keystrokes into the frontmost app):
#   1. FX_TRACKS (default: the vocal FX returns) replace their same-named tracks with
#      ALL track data (plug-ins, settings, sends, outputs, faders).
#   2. MASTER_TRACKS (default: MASTER BUS) take ONLY main outputs and sends, so the
#      target keeps its own master chain and its Metric AB reference.
# Each target is opened, imported, checked with strips.py and saved. Pro Tools holds one
# session at a time, so whatever is open gets closed (save it first).
# Template update = run this against a session created from the template, then
# File > Save As Template (see references/session-prep.md, "Updating your template").
set -u
SRC="$1"; shift
DIR="$(cd "$(dirname "$0")" && pwd)"; P="$DIR/.venv/bin/python"
IFS=$'\n' read -r -d '' -a FX <<< "${FX_TRACKS:-V. PLATE
V. HALL
V. CHAMBER
V. SLAP
V. THROW
V. ADT
Para VOX}"
IFS=$'\n' read -r -d '' -a MASTER <<< "${MASTER_TRACKS:-MASTER BUS}"
# Open-panel path: the home folder sidebar item, then each folder below it.
REL="${SRC#$HOME/}"; IFS='/' read -r -a NAV <<< "$REL"
HOMEITEM="$(basename "$HOME")"
cd "$DIR"

imp() {  # imp <trackdata args...> -- <track>...
  local td=(); while [ "$1" != "--" ]; do td+=("$1"); shift; done; shift
  $P ptax.py menu File Import "Session Data..." >/dev/null || return 1; sleep 2.5
  $P ax_open_panel.py "$HOMEITEM" "${NAV[@]}" | tail -1; sleep 3
  for t in "$@"; do
    $P isd.py set "$t" "$t" || { $P ptax.py click --window "Import Session Data" Cancel; return 1; }
  done
  $P ptax.py click --window "Import Session Data" "Choose..." >/dev/null; sleep 1.5
  $P trackdata.py "${td[@]}" >/dev/null
  $P ptax.py click --window "Track Data to Import" OK >/dev/null; sleep 1
  $P ptax.py click --window "Import Session Data" OK >/dev/null; sleep 8
}

for T in "$@"; do
  echo "== $(basename "$T" .ptx) $(date +%T)"
  $P opensess.py "$T" | tail -1 || continue
  sleep 5
  imp all -- "${FX[@]}" || echo "IMPORT FX FAILED"
  imp only "Main Output Assignments" "Send Output Assignments" "Send Volume Automation and Setting" \
      "Send Pan Automation and Setting" "Send Mute Automation and Setting" -- "${MASTER[@]}" || echo "IMPORT MASTER FAILED"
  $P strips.py "${MASTER[@]}" "${FX[@]}"
  $P ptctl.py exec "e.save_session()" >/dev/null 2>&1 && echo "SAVED $(date +%T)"
done

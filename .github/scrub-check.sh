#!/usr/bin/env bash
# Scrub check for show-file-skills. Blocks personal details, secrets, client
# names, binaries and show files from landing in this public repo.
# Usage: scrub-check.sh [repo-dir] [private-denylist-file]
# The private denylist (client names etc.) is kept out of the repo. In CI it
# comes from the SCRUB_DENYLIST secret; hits on it print file:line only so the
# list itself never shows up in a public log.
set -uo pipefail
DIR=${1:-.}
PRIVATE=${2:-}
cd "$DIR"
fail=0
files() { git ls-files -co --exclude-standard -z -- . ':!.github/scrub-check.sh'; }

# Public patterns: PCRE, case-insensitive.
PUBLIC=(
  'michaelkeithlewis(?!/show-file-skills)'
  '/home/[a-z]'
  '/Users/[A-Za-z]'
  '\b100\.(6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\.[0-9]{1,3}\.[0-9]{1,3}\b'
  '\b192\.168\.[0-9]{1,3}\.[0-9]{1,3}\b'
  '\b172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3}\b'
  '[A-Za-z0-9._%+-]+@(?!example\.(com|org)|users\.noreply\.github\.com)[A-Za-z0-9-]+\.[A-Za-z0-9.-]*[a-z]{2,}'
  '(?<![\d.])\(?[2-9]\d{2}\)?[-. ]\d{3}[-. ]\d{4}(?![\d.])'
  '\+\d{1,3}[ -]?\(?\d{2,4}\)?[ -]?\d{3,4}[ -]?\d{3,4}\b'
  '\bpass show\b'
  'sk-ant-'
  'ghp_[A-Za-z0-9]'
  'github_pat_'
  'xox[abpr]-'
  'AKIA[0-9A-Z]{16}'
  '-----BEGIN [A-Z ]*PRIVATE KEY'
  'tailscale|\.ts\.net\b'
)
for pat in "${PUBLIC[@]}"; do
  if hits=$(files | xargs -0 -r grep -nIiP -- "$pat" 2>/dev/null); then
    echo "BLOCKED [$pat]:"; echo "$hits" | head -10; fail=1
  fi
done

# Private patterns: report location only.
if [[ -n "$PRIVATE" && -s "$PRIVATE" ]]; then
  n=0
  while IFS= read -r pat; do
    [[ -z "$pat" || "$pat" == \#* ]] && continue
    n=$((n+1))
    if hits=$(files | xargs -0 -r grep -nIiPo -- "$pat" 2>/dev/null | cut -d: -f1,2); then
      echo "BLOCKED [private pattern #$n] at:"; echo "$hits" | head -10; fail=1
    fi
  done < "$PRIVATE"
else
  echo "note: no private denylist given, client-name check skipped"
fi

# No binaries, audio, archives or show files.
if bad=$(git ls-files -co --exclude-standard | grep -iE '\.(ses|tar\.gz|tgz|bin|dll|exe|rack2|ptx|dsh|logicx|zip|wav|aiff?|mp3|flac|m4a|show)$'); then
  echo "BLOCKED FILE TYPES:"; echo "$bad"; fail=1
fi
# Every script compiles (compile only, nothing runs). No em-dashes in prose.
while IFS= read -r -d '' f; do
  python3 - "$f" <<'PY' || { echo "PY COMPILE FAILED: $f"; fail=1; }
import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")
PY
done < <(git ls-files -co --exclude-standard -z '*.py')
if dash=$(git ls-files -co --exclude-standard -z '*.md' | xargs -0 -r grep -nl $'—'); then
  echo "EM-DASH in:"; echo "$dash"; fail=1
fi

[[ $fail -eq 0 ]] && echo "scrub check passed" || echo "scrub check FAILED"
exit $fail

#!/usr/bin/env bash
# Print the CHANGELOG.md section for one version, without its heading.
# Usage: release-notes.sh 1.2.3 [CHANGELOG.md]
# Exits 1 when the section is missing, empty, or still has unreleased changes above it.
set -euo pipefail

version="${1:?usage: release-notes.sh VERSION [CHANGELOG.md]}"
changelog="${2:-CHANGELOG.md}"

# A newer change may have landed since the release notes were cut. The package
# would contain it even though this version's notes would omit it.
if ! awk '
  /^## \[Unreleased\][[:space:]]*$/ { pending = 1; next }
  pending && /^## \[/ { exit }
  pending && /[^[:space:]]/ && !/^\[[^]]+\]: / { exit 1 }
' "$changelog"; then
  echo "move the entries under [Unreleased] into [${version#v}] before tagging" >&2
  exit 1
fi

# index() rather than a regex, so the dots in the version match only dots. The section
# ends at the next heading; trailing version comparison links are omitted.
notes="$(awk -v head="## [${version#v}]" '
  index($0, head " - ") == 1 && substr($0, length(head) + 4) ~ /^[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9][[:space:]]*$/ {
    found = 1
    next
  }
  found && /^## \[/ { exit }
  found { lines[++n] = $0 }
  END {
    tail = n
    while (tail > 0 && (lines[tail] ~ /^[[:space:]]*$/ || lines[tail] ~ /^\[[^]]+\]: /)) tail--
    for (i = 1; i <= n; i++) {
      if (i > tail && lines[i] ~ /^\[(Unreleased|v?[0-9]+\.[0-9]+\.[0-9]+[^]]*)\]: /) continue
      print lines[i]
    }
  }
' "$changelog")"

if ! grep -q '[^[:space:]]' <<<"$notes"; then
  echo "no dated, nonempty '## [${version#v}]' section in $changelog" >&2
  exit 1
fi
printf '%s\n' "$notes"

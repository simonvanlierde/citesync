# 0004. Python 3.12 and ruamel.yaml

- Status: accepted
- Date: 2026-10-28

## Context

With a pluggable source ([0001](0001-pluggable-source.md)), CITATION.cff is a file citesync writes. Every real CFF file checked when this was decided had comments, and losing them would make `write` unusable. Rust, the other candidate, had no maintained YAML writer that keeps comments.

## Decision

citesync is written in Python 3.12 or newer, and uses ruamel.yaml for YAML round trips.

## Consequences

- `write` keeps comments, key order and quoting in CITATION.cff and `_extension.yml`. The few changes it still makes are listed in [How write works](../write.md#safety).
- The pre-commit hook and the browser playground run the same Python code.
- Revisit if a Rust YAML writer that keeps comments becomes maintained.

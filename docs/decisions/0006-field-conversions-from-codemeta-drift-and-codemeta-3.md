# 0006. Every field conversion comes from codemeta-drift, and CodeMeta 3.0 is the default

- Status: accepted
- Date: 2026-11-01 (field conversions); 2026-10-28 (CodeMeta 3.0)

## Context

[0002](0002-vendored-mapping.md) put field locations in a mapping vendored from codemeta-drift. Two questions stayed open. Where does a missing format or field go? And which CodeMeta version does `write` emit while CodeMeta 4.0 exists?

## Decision

Every field conversion comes from a codemeta-drift row. A missing format or field is added to codemeta-drift first, then the pinned mapping here is updated. How a value is spelled stays in citesync.

`write` emits CodeMeta 3.0 for a new `codemeta.json`. The version to emit is rechecked by 2027-04-28: does the Software Heritage indexer read the 4.0 context? On 2026-11-01 it still read only 2.0 and 3.0.

## Consequences

- A new format or field needs a codemeta-drift change and a reviewed repin before citesync can use it.
- citesync holds no field locations of its own.
- Until the recheck, `codemeta.json` files written by citesync stay readable by Software Heritage.
- If the recheck finds 4.0 supported, the default changes in a new record that supersedes the 3.0 part of this one.

# Any supported file can be the source

- Status: accepted
- Date: 2026-10-28

## Context

The files citesync compares have to agree with one file. Which one? A repo with a CITATION.cff wants that file. A repo that has only pyproject.toml, Cargo.toml or package.json wants its manifest. Some source files cannot hold every field: pyproject.toml and Cargo.toml have no ORCID or DOI slot, and package.json has no ORCID.

## Decision

The source is pluggable. Any supported file can be the source, and CITATION.cff is the default (`--source` or the `source` config key picks another).

When the source has no slot for a field, the other files that hold it must agree with each other. The report says so, and `write` leaves that field alone. A source field that is present but empty counts as no slot.

## Consequences

- One tool serves repos with and without a CITATION.cff.
- The source can be a file citesync has to write to, not only read. That is why [Python 3.12 and ruamel.yaml](python-and-ruamel.md) needs a YAML writer that keeps comments.
- The rules for a missing slot live in [How check works](../check.md); keep them there.

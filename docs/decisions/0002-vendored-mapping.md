# 0002. Field locations come from a vendored mapping, in a separate repo

- Status: accepted
- Date: 2026-10-28

## Context

Each file format keeps a field in a different place (CFF `title` is CodeMeta `name`). CodeMeta publishes crosswalks for this. Reading them live, or copying them by hand, would drift from the spec.

## Decision

[codemeta-drift](https://github.com/simonvanlierde/codemeta-drift) is a separate repo. It owns the crosswalk data and exports a mapping file with a JSON Schema. citesync vendors a copy in `src/citesync/`, pinned to a codemeta-drift release in `MAPPING_SOURCE` with the sha256 of each file. A test checks the hashes.

The mapping says where a field sits. How a value is written (SPDX id or URL, ORCID URL or bare iD, `Family, Given`) stays in citesync as one codec per format and field, each with an inverse for writing.

An unknown major `schema_version`, or no row for a compared field in a format citesync reads, is exit 2.

Two repos, not one, so the hub can move to the CodeMeta organisation whole if they ask for it.

## Consequences

- Adopting a new mapping needs a codemeta-drift release and a reviewed repin.
- A new or changed mapping row can make existing CI fail, so it is a minor release with a changelog note.
- The mapping holds paths only. Shapes a path cannot express (Cargo `.workspace = true`, npm `author` as string or object) stay in the format adapters.

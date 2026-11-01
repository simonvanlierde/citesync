# Shared structured-name cases

This is an unchanged copy of CRediT Matrix's `conformance/names/people-v1.json`.
`SOURCE.json` records the source path, Git blob revision and SHA-256 of these bytes.
The revision identifies file content, not a release or commit.

To update, review the canonical cases, copy the JSON without reformatting, and record
`git hash-object people-v1.json` and `sha256sum people-v1.json` in `SOURCE.json`.
The tests verify both hashes. Update all three repositories together.

Structured name fields are authoritative. Display names alone do not establish family order.
Each tool keeps its own validation rules; a normalized ORCID is not necessarily checksum-valid.

The corpus is copied under CRediT Matrix’s MIT license, retained in `LICENSE`.

Citesync preserves the source Unicode spelling and compares names in NFC. The canonical
`codemeta` expectations describe normalized identity, not a required rewrite of source text.

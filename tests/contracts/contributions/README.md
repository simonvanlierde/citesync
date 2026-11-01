# Contribution contract fixture

These files are a hand-written integration example. `expected.json` was written
from the formats' field meanings, before running the converter; do not regenerate
it from citesync output. The CLI tests copy only the four input files into a
temporary directory, so the tracked inputs stay unchanged.

The historical names are test labels. The identities and affiliations are
fictional combinations, not assertions about those people. The ORCID
`0000-0002-1825-0097` is the published fictional Josiah Carberry example. The
missing ORCIDs are deliberate and must stay missing.

- `codemeta.json` supplies author and contributor Person records by hand. Its
  author Role follows the shape of CRediT Matrix's exporter at
  [`b39d3aa`](https://github.com/simonvanlierde/credit-matrix/blob/b39d3aa992c6779e701a87946cdbf527279e9a69/src/core/export/codemeta.ts).
  No producer-generated Person export is claimed.
- `CITATION.cff` and `.zenodo.json` start with an abbreviated author name. The
  shared ORCID permits a rename without dropping affiliations or name particles.
- `expected.json` fixes the expected people in each target. The non-author stays
  a contributor; Zenodo's `DataManager` type stays unchanged. No Role becomes a
  Person or supplies a Zenodo type.
- `citesync.toml` explicitly selects CodeMeta as the source and disables manifest
  discovery. Tests also select CFF to exercise writing a CodeMeta target.

The tests use the vendored mapping whose release, commit and artifact hashes are
in [`MAPPING_SOURCE`](../../../src/citesync/MAPPING_SOURCE). Existing mapping
tests verify those hashes. No remote fetch or producer installation is required.

See [the contribution guide](../../../docs/contributions.md) for supported shapes,
format losses and remaining producer work.

## Matrix producer inputs

`matrix-roster.json` and `matrix-attribution.json` copy the native roster and
hand-checked CodeMeta expectation from Matrix commit
`a8a55c648bbb45862d60fbdbd6d51cd75eea3cc3`, under
`src/core/__tests__/fixtures/export-codemeta{,.expected}.json`.
The names and reserved identifiers are the same as the existing contribution example.
Their MIT licence is in `MATRIX-LICENSE`.

- `matrix-roster.json` SHA-256: `65d930d8c62987f88d3751f9206cfb3a1541838befd90ae79b81d67a807045fb`
- `matrix-attribution.json` SHA-256: `5f7283afd7d9c6215c0776bacf2f57798ba9143075d8adba835ceec206bee4d0`

The existing playground CI job installs the pinned `credit-matrix@0.10.0`
development dependency and runs `tests/test_matrix_consumer.py`. The producer
expectation is compared before citesync runs; `expected.json` remains the
independent oracle for CFF and Zenodo. Python-only runs skip these four tests
when Node dependencies are not installed.

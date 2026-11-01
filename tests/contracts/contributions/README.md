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

# 0007. Check the metadata that ships with a release

- Status: accepted
- Date: 2026-11-26

## Context

Citation files can agree in a checkout while the built package carries a different version or licence. Required-field checks also find gaps in existing citation files that `write` currently leaves for a maintainer to fill.

## Decision

Start with a CiteSync release. Compare the wheel and source distribution with `CITATION.cff`, `codemeta.json` and `.zenodo.json` using the existing read-only Python metadata reader. Check the required fields each format can carry. Record the input for each comparison, the pinned mapping version, and any values that differ or that a format cannot represent. Publish the commands and a before-and-after example so another project can repeat the check in CI.

Extend [0003](0003-manifests-opt-in.md) to allow a maintainer to opt in to filling named fields in selected citation files. Fill a field only when the selected source supplies a value and the pinned mapping and target format can represent it. Show the addition in `write --diff`. By default, `write` preserves omissions. Package-manifest writes require their separate opt-in.

Run the pilot using the [single-source model](0001-pluggable-source.md). If a release still requires copying a fact by hand because different inputs own different fields, record that case before proposing per-field source selection.

## Consequences

- CiteSync reads metadata from artifacts produced by the project's existing build. The pilot uses extracted `METADATA` and `PKG-INFO` as inputs.
- Field locations come from [codemeta-drift](0002-vendored-mapping.md). Contribution roles stay in CodeMeta, with Zenodo types supplied explicitly as described in [0005](0005-vocabulary-blind-roles.md).
- The worked example is the starting point for an outside pilot and a reusable template check. Running these comparisons verifies agreement on the fields checked. Archive ingestion needs its own test.

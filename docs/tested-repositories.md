# Tested on real repositories

The tests copy the metadata files of five public repositories byte for byte (commits in [tests/fixtures/SOURCES.txt](../tests/fixtures/SOURCES.txt)) and check that citesync reports exactly these findings, with CITATION.cff as the source.

| Repository | Config | Findings | Exit | Why |
| --- | --- | --- | ---: | --- |
| sourceledger | none | none | 0 | codemeta.json uses the CodeMeta 4.0 context, which passes with `codemeta-version` unset; `codemeta-version = "3.0"` makes it a `context-mismatch`. pyproject.toml and .zenodo.json agree on every field |
| credit-matrix | none | codemeta.json `name-mismatch` | 1 | codemeta.json names it "CRediT Matrix", CITATION.cff "CRediT Matrix: drafting CRediT contribution statements with co-authors". The root package.json is private, so it is skipped |
| credit-matrix | `manifests = ["src/core/package.json"]` | codemeta.json `name-mismatch` | 1 | As above. The package agrees: its version, licence and author match, its keywords are a subset, and its `git+…/credit-matrix.git` repository names the same repository |
| jsonvet | none | Cargo.toml `keywords-not-subset` | 1 | The workspace keywords include `lint`, and CITATION.cff has `linter`. Only Cargo.toml holds a version, so there is nothing to compare it with |
| jsonvet | `manifests = ["crates/jsonvet-cli/pyproject.toml"]` | that pyproject.toml `keywords-not-subset`; `not-checked` version (info) | 1 | The same keyword. The list replaces the root manifests and the pyproject version is `dynamic`, so no file holds a version |
| r9lab | none | none | 0 | As sourceledger. The root pyproject.toml has no `[build-system]` and the root package.json is private, so no manifest is checked |
| project-templates | none | `not-checked` version (info) | 0 | CITATION.cff alone, with no version |

A made-up set where all six files agree exits 0 with each of them as the source.

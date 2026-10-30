# Tested on real repositories

The tests hold exact copies of the metadata files from five public repositories, at the commits in [tests/fixtures/SOURCES.txt](../tests/fixtures/SOURCES.txt). With CITATION.cff as the source, citesync must report exactly these findings.

| Repository | Config | Findings | Exit | Why |
| --- | --- | --- | ---: | --- |
| sourceledger | none | none | 0 | codemeta.json uses CodeMeta 4.0, which passes while `codemeta-version` is unset. pyproject.toml and .zenodo.json agree on every field |
| credit-matrix | none | codemeta.json `name-mismatch` | 1 | codemeta.json's name is "CRediT Matrix". CITATION.cff's title adds ": drafting CRediT contribution statements with co-authors". The root package.json is private, so citesync skips it |
| credit-matrix | `manifests = ["src/core/package.json"]` | codemeta.json `name-mismatch` | 1 | As above. The package agrees on version, licence, author, keywords and repository |
| jsonvet | none | Cargo.toml `keywords-not-subset` | 1 | Cargo.toml has the keyword `lint`, and CITATION.cff has `linter`. Only Cargo.toml holds a version, so there is nothing to compare it with |
| jsonvet | `manifests = ["crates/jsonvet-cli/pyproject.toml"]` | that pyproject.toml `keywords-not-subset`; `not-checked` version (info) | 1 | The same keyword. That pyproject version is `dynamic`, so no file holds a version |
| r9lab | none | none | 0 | As sourceledger. citesync checks no manifest: the root pyproject.toml has no `[build-system]` and the root package.json is private |
| project-templates | none | `not-checked` version (info) | 0 | CITATION.cff alone, with no version |

A made-up set where all six files agree exits 0 with each of them as the source.

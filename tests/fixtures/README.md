# Test fixtures

Real metadata files copied byte for byte from public repositories, plus a synthetic all-agree set. In the synthetic set, package.json lists a contributor (Grace Hopper) whom no other file names: a tripwire that fails if `contributors` is ever read as authors, which v0.1 leaves out. Its .zenodo.json lists a paper DOI before the repository under `isSupplementTo`, so the repository URL must be picked from among them. test_check.py plants one disagreement at a time in a copy of this set. `SOURCES.txt` lists each copied file as `<owner/repo> <commit sha> <path> <sha256>`. Each directory's `cases.json` holds the findings citesync must report, derived by hand from the comparison rules, not from running citesync. Each `record.json` holds, by hand, the record citesync should read from every metadata file in that directory: CodeMeta terms, ORCIDs as bare iDs, whitespace collapsed.

NOTICE: these files are copied from the repositories below and keep their licences.

- simonvanlierde/sourceledger: MIT
- simonvanlierde/credit-matrix: MIT
- simonvanlierde/jsonvet: MIT
- CMLPlatform/r9lab: AGPL-3.0
- simonvanlierde/project-templates: MIT

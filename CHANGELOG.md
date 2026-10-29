# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `citesync check`: compares title/name, version, authors with ORCID, licence, DOI, repository URL, description and keywords across CITATION.cff, codemeta.json, .zenodo.json, pyproject.toml, Cargo.toml and package.json, with any of them as the source. Exit 0 when they agree, 1 on findings, 2 when it couldn't check.
- Output as text, JSON (`--format json` or `--json`, with `schema_version`) or GitHub workflow annotations (`--format github`).
- `citesync config`, and config discovery from `citesync.toml`, `.citesync.toml`, pyproject.toml, Cargo.toml or package.json.
- The field mapping, vendored from codemeta-drift with its JSON Schema.

[Unreleased]: https://github.com/simonvanlierde/citesync/commits/HEAD

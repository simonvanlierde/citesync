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
- Keywords compare case-insensitively, as author names do, so `LCA` matches `lca`. Set `keywords_case_sensitive = true` in the config to compare them by case.
- Repository URLs compare by the repository they name: `http://www.github.com/Owner/Repo/tree/v1.0` matches `https://github.com/owner/repo`. Branch, tag and file pages count on GitHub, GitLab, Codeberg, Gitea and Bitbucket; paths ignore case on GitHub only. Findings show the URLs as written.
- Versions compare as PEP 440 versions, so `v1.2.3` matches `1.2.3`, `1.0` matches `1.0.0` and `0.3.1-rc.1` matches `0.3.1rc1`. A version that isn't PEP 440, such as `unreleased`, must match exactly.

[Unreleased]: https://github.com/simonvanlierde/citesync/commits/HEAD

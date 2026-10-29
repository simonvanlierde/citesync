# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `citesync check`: compares title/name, version, authors with ORCID, licence, DOI, repository URL, description and keywords across CITATION.cff, codemeta.json, .zenodo.json, pyproject.toml, Cargo.toml and package.json, with any of them as the source. Exit 0 when they agree, 1 on an error finding, 2 when citesync couldn't run (a bad config or option, a missing source file, an internal error).
- Each finding names its rule, such as `version-mismatch` or `keywords-not-subset`, and has a severity. `citesync rules` lists the rules and `citesync explain <rule>` describes one; [docs/rules.md](docs/rules.md) has them all.
- A file citesync can't read or parse is an `unreadable` finding, with the parser's line and column when it gives them, and the other files are still checked against each other.
- Output as text, JSON (`--format json` or `--json`) or GitHub workflow annotations (`--format github`). Text is coloured on a terminal (`NO_COLOR` and `FORCE_COLOR` are honoured) and ends with a summary line; `--quiet` prints only errors. JSON is one document with a `version`, the tool, a summary and the findings, each with its rule, severity, help, a link to the rule's docs and its position when known. GitHub output ends with a notice that counts the findings. JSON always lists every finding, whatever `-q` or `-v` say.
- A JSON compatibility policy: a minor release may add rule ids and optional fields, so ignore what you don't know; removing or retyping a field bumps the report's `version`, in a major release.
- `citesync --version`.
- `ignore` in the config drops the findings of the rules it lists, and warns about an entry that matched nothing.
- `citesync config`, and config discovery from `citesync.toml`, `.citesync.toml`, pyproject.toml, Cargo.toml or package.json. Config keys are kebab-case, such as `codemeta-version`.
- The field mapping, vendored from codemeta-drift with its JSON Schema.
- Keywords compare case-insensitively, as author names do, so `LCA` matches `lca`. Set `keywords-case-sensitive = true` in the config to compare them by case.
- Repository URLs compare by the repository they name: `http://www.github.com/Owner/Repo/tree/v1.0` matches `https://github.com/owner/repo`. Branch, tag and file pages count on GitHub, GitLab, Codeberg, Gitea and Bitbucket; paths ignore case on GitHub only. Findings show the URLs as written.
- A codemeta.json `identifier` given as a schema.org PropertyValue is read as a DOI when its `propertyID` is `DOI` or its `value` or `url` is a DOI. Other PropertyValues, such as a SWHID or a ROR id, are skipped.
- Versions compare as PEP 440 versions, so `v1.2.3` matches `1.2.3`, `1.0` matches `1.0.0` and `0.3.1-rc.1` matches `0.3.1rc1`. A version that isn't PEP 440, such as `unreleased`, must match exactly.
- `citesync write`: rewrites the citation files that disagree with the source, and the manifest fields listed in `write-manifests`, keeping comments, key order and formatting. Fields a file leaves out stay out. It reports the findings left as `check` does, each saying what to do, and never writes an ignored finding or an unreadable file. Exit 0 when the files agree afterwards, 1 when an error finding remains, 2 when it couldn't run and wrote nothing.

[Unreleased]: https://github.com/simonvanlierde/citesync/commits/HEAD

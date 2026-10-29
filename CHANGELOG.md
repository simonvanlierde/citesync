# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- When a repo has no .zenodo.json, Zenodo reads CITATION.cff, so two rules check it. `zenodo-license-list` is an error for a `license` list, which Zenodo refuses. `zenodo-drops-field` warns about `identifiers` and `references`, which Zenodo leaves out of the record; a Zenodo DOI among the identifiers is fine.
- A keyword that differs from another file's only in hyphens, underscores or spaces is named in the finding, as in `industrial-ecology (CITATION.cff has 'industrial ecology': differs only in separators)`. `citesync write` gives it the source's spelling where it stands, instead of dropping it.
- `keywords-ignore-separators = true` treats such keywords as equal. Against Cargo.toml they always are, since crates.io refuses a keyword with a space.

### Fixed

- `python -m citesync` runs the command line, as `citesync` does. It failed with "No module named citesync.__main__".

## [0.1.0] - 2026-10-29

### Added

- `citesync check`: compares title/name, version, authors with ORCID, licence, DOI, repository URL, description and keywords across CITATION.cff, codemeta.json, .zenodo.json, pyproject.toml, Cargo.toml and package.json, with any of them as the source. Exit 0 when they agree, 1 on an error finding, 2 when citesync couldn't run (a bad config or option, a missing source file, an internal error).
- Each finding names its rule, such as `version-mismatch` or `keywords-not-subset`, and has a severity. `citesync rules` lists the rules and `citesync explain <rule>` describes one; [docs/rules.md](docs/rules.md) has them all.
- A file citesync can't read or parse is an `unreadable` finding, with the parser's line and column when it gives them, and the other files are still checked against each other.
- Output as text, JSON (`--format json` or `--json`) or GitHub workflow annotations (`--format github`). Text is coloured on a terminal (`NO_COLOR` and `FORCE_COLOR` are honoured) and ends with a summary line; `--quiet` prints only errors. JSON is one document with a `version`, the tool, a summary and the findings, each with its rule, severity, help, a link to the rule's docs and its position when known. GitHub output ends with a notice that counts the findings. JSON always lists every finding, whatever `-q` or `-v` say.
- A JSON compatibility policy: a minor release may add rule ids and optional fields, so ignore what you don't know; removing or retyping a field bumps the report's `version`, in a major release.
- `citesync --version`.
- Without `--root`, citesync walks up from the current directory to the nearest directory with a citation file or a citesync config, stopping at the git root.
- A `role-dangling` warning for a CodeMeta `Role` in codemeta.json's `author` or `contributor` list, such as a CRediT role from credit-matrix, whose `schema:author` ORCID no listed person has. `write` keeps Roles as they are.
- A pre-commit hook, `citesync`, for prek or pre-commit. It runs `citesync check` when a commit changes a citation file, a package manifest or citesync's config, at any depth, and fails the commit on an error finding.
- A manual-stage hook, `citesync-write`, that runs `citesync write` when you ask for it.
- `ignore` in the config drops the findings of the rules it lists, and warns about an entry that matched nothing.
- `citesync config`, and config discovery from `citesync.toml`, `.citesync.toml`, pyproject.toml, Cargo.toml or package.json. Config keys are kebab-case, such as `codemeta-version`.
- The field mapping, vendored from codemeta-drift 0.1.0 with its JSON Schema.
- An author with only a name, such as an organization, compares as a family name in CITATION.cff, codemeta.json and .zenodo.json, and write keeps it.
- Keywords compare case-insensitively, as author names do, so `LCA` matches `lca`. Set `keywords-case-sensitive = true` in the config to compare them by case. codemeta.json may give them as one comma-separated string, as schema.org allows.
- Repository URLs compare by the repository they name: `http://www.github.com/Owner/Repo/tree/v1.0` matches `https://github.com/owner/repo`. Branch, tag and file pages count on GitHub, GitLab, Codeberg, Gitea and Bitbucket; paths ignore case on GitHub only. Findings show the URLs as written.
- A codemeta.json `identifier` given as a schema.org PropertyValue is read as a DOI when its `propertyID` is `DOI` or its `value` or `url` is a DOI. Other PropertyValues, such as a SWHID or a ROR id, are skipped.
- Versions compare as PEP 440 versions, so `v1.2.3` matches `1.2.3`, `1.0` matches `1.0.0` and `0.3.1-rc.1` matches `0.3.1rc1`. A version that isn't PEP 440, such as `unreleased`, must match exactly.
- `citesync write`: rewrites the citation files that disagree with the source, and the manifest fields listed in `write-manifests`, keeping comments, key order, formatting and CRLF line ends, and writing through symlinks. Fields a file leaves out stay out. A value a file can't hold without losing something is left for you, with the reason: a compound licence in .zenodo.json, an `AND` licence in CITATION.cff or codemeta.json, a version semver can't spell in Cargo.toml or package.json, a version that isn't PEP 440 in pyproject.toml, or a renamed author whose old entry holds an email or affiliation. It reports the findings left as `check` does, each saying what to do, and never writes an ignored finding or an unreadable file. Exit 0 when the files agree afterwards, 1 when an error finding remains, 2 when it couldn't run and wrote nothing.
- `citesync write --diff` prints the edits write would make as a unified diff and writes nothing. Exit 0 when there is nothing to change, 1 when there is or when a file can't be read (listed on stderr), as `ruff format --diff` does.

[Unreleased]: https://github.com/simonvanlierde/citesync/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/simonvanlierde/citesync/releases/tag/v0.1.0

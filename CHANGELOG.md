# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

To upgrade from 0.1.0:

- `citesync check` has four new error rules: `contributor-mismatch`, `date-mismatch`, `zenodo-license-list` and `file-missing`. To turn any of them off for now, list it under `ignore` ([docs/rules.md](docs/rules.md)).
- `codemeta-version` no longer defaults to 3.0. To keep checking codemeta.json's `@context` as before, set `codemeta-version = "3.0"`.
- Use citesync through its command line or the pre-commit hook. Its Python modules are internal and may change in any release.
- `write-manifests` takes only `version`, `author`, `contributor`, `license`, `codeRepository` and `keywords`, the fields a manifest holds. Take any other field off the list.
- The text output changed: each finding starts with `file:line:col` and has a `help:` line under it, a failing check ends with an `N fixable` line, and `citesync write` ends with `N fixed, M left in K files`. In GitHub output, each annotation ends with its `help:` line and the `::notice::` line gives write's new count, so scripts should read `--format json` instead ([docs/output.md](docs/output.md)).

### Added

- `citesync init` writes a CITATION.cff from codemeta.json, .zenodo.json and the package manifests when a repo has none, so `citesync check` passes from the start ([docs/init.md](docs/init.md)).
- Contributors are compared across codemeta.json, .zenodo.json and package.json, the same way as authors (`contributor-mismatch`).
- Release dates are compared across CITATION.cff, codemeta.json and .zenodo.json (`date-mismatch`).
- `version-behind-tag` warns when the source's version is older than the repo's newest git tag.
- `--format sarif` prints a SARIF log that GitHub code scanning can upload.
- `citesync write` creates codemeta.json when the `files` setting lists it and it doesn't exist yet.
- `citesync --help` lists the exit codes and where config is read from. `citesync` with no command prints the help.
- Two rules for repos where Zenodo reads CITATION.cff: `zenodo-license-list` and `zenodo-drops-field`.
- A keyword that differs from another file's only in hyphens, underscores or spaces is named as such, and `citesync write` gives it the source's spelling. `keywords-ignore-separators = true` treats such keywords as equal.
- A failing `citesync check` says how many findings `citesync write` would fix, and `citesync write` how many it fixed and left ([docs/check.md](docs/check.md#findings-and-exit-codes)).
- `-v` names each manifest check left out, and why (`manifest-skipped`). `citesync config` prints the repo root in use.
- `--color auto|always|never` sets colour whatever `NO_COLOR` and `FORCE_COLOR` say, and `-V` is short for `--version`.
- Each finding on a key gives the key's line and column, so an editor or code scanning can jump to it ([docs/output.md](docs/output.md)).
- A mistyped rule id, `--format` value or `write-manifests` field gets a "did you mean" suggestion. On Python before 3.14, option values get none.

### Changed

- **Breaking:** `codemeta-version` has no default. When it's unset, any CodeMeta version passes and `citesync write` leaves `@context` alone.
- **Breaking:** a file listed in the `files` setting that doesn't exist is a `file-missing` error. 0.1.0 skipped it.
- The field mapping comes from codemeta-drift 0.2.0, which adds contributors and release dates.
- `citesync check` starts about a third faster.
- **Breaking:** `write-manifests = "all"` means the six manifest fields, and naming any other field is a config error.
- A keyword finding between citation files lists the missing and extra words, not both files' lists.
- A missing source file names the directory citesync looked in. Run outside any citation files, citesync uses the git root, and `--root` must be a directory.
- A bad `ignore` entry is named in the error, and an unquoted `codemeta-version = 3.0` says to write it as a string ([docs/config.md](docs/config.md)).
- The warning about an unused `ignore` entry is quiet under `-q`.

### Fixed

- `citesync write` wrote a CITATION.cff entity (an author with only a name) to codemeta.json as a `Person`. It's now an `Organization`.
- `citesync write` reformatted the existing entries of a JSON author list when it added an author.
- `python -m citesync` failed with "No module named `citesync.__main__`".
- With `doi: ""` in CITATION.cff, the DOI under `identifiers` was ignored.
- codemeta.json entries written with `type` and `id` instead of `@type` and `@id` were ignored.
- A name in one string, such as codemeta.json `name`, written family name first (`Tu Youyou`, `屠呦呦`) was an `author-mismatch` against CITATION.cff's given and family names, and `citesync write` rewrote it.
- A title with an accent typed two different ways didn't match itself.
- `citesync write` folded an author's `name-particle` and `name-suffix` into `family-names` when it changed the given name.
- GitHub annotations didn't attach to their files when the root was a subdirectory of the git repo.
- codemeta.json keywords given as one string weren't split on full-width (`，`) or ideographic (`、`) commas.
- A manifest or .zenodo.json that starts with a byte order mark gave a confusing parser error.
- A file behind a symlink that points out of the repo was read, and `write` could change it. It's now `unreadable`.
- Control characters in a file could retitle the terminal or hide lines. They now print as `\xNN`.
- Printing non-ASCII text to a stdout that isn't UTF-8, such as a Windows pipe, crashed.
- Some inputs made `citesync check` run for minutes, such as an author string with a long run of spaces or a keyword list thousands long.
- A repository URL with whitespace before a trailing slash, such as `https://example.org/r /`, kept that whitespace when read.
- `citesync write` dropped the comments above a `---` line at the top of CITATION.cff.
- An author with an ORCID and no name was written to pyproject.toml, Cargo.toml or package.json as an empty entry, one more on each run. `citesync write` now leaves that list for a hand edit and says why.
- `citesync write` turned every line end of a file with both LF and CRLF line ends into CRLF, even when it changed nothing else. It now keeps the more common one ([docs/write.md](docs/write.md#safety)).

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

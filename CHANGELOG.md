# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

To upgrade from 0.1.0:

- `citesync check` can fail on rules 0.1.0 didn't have: `contributor-mismatch`, `date-mismatch`, `zenodo-license-list` and `file-missing`. To keep 0.1.0's results for now, list the ones you don't want under `ignore`.
- `codemeta-version` no longer defaults to 3.0. To keep checking codemeta.json's `@context` as 0.1.0 did, set `codemeta-version = "3.0"`.
- Use citesync through its command line and the pre-commit hook. Its Python modules are internal and may change in any release.

### Added

- Contributors are compared as authors are: codemeta.json `contributor`, .zenodo.json `contributors` and package.json `contributors`. CITATION.cff has no contributor list, so with it as the source those files must agree with each other. Only the people count, never a CodeMeta Role or a Zenodo contributor `type`. A difference is a `contributor-mismatch` error. `citesync write` renames and reorders contributors, but leaves a new Zenodo contributor for a hand edit, since Zenodo needs a type for each one.
- The release date is compared: CFF `date-released`, CodeMeta `datePublished` and Zenodo `publication_date`, by day, so a time after the date doesn't count. A difference is a `date-mismatch` error, and `citesync write` fixes it as `YYYY-MM-DD`.
- `version-behind-tag` warns when the source's version is older than the repo's newest git tag, as after a release tagged without bumping CITATION.cff. citesync reads the tags from `.git` itself, so it runs no `git`, and finds it from a root in a subdirectory too.
- `citesync check --format sarif` (and `write`) prints a SARIF 2.1.0 log that GitHub code scanning can upload with `github/codeql-action/upload-sarif`. Each file is named by its path in the repo, and a finding on no file is left out, since it has nowhere to point.
- `citesync write` creates codemeta.json when the `files` setting lists it, at the root or in a subdirectory, and it doesn't exist yet. It takes the configured `codemeta-version`, else 3.0, and leaves out a field codemeta.json can't spell, such as a licence with `AND`, saying why on its `wrote` line. It creates nothing from a source it can't read, and `write --diff` shows the new file as a diff from `/dev/null`.
- `citesync --help` and `citesync check --help` give the exit codes, where config is read from and a link to the docs. `citesync` with no command prints the help and exits 2.
- When a repo has no .zenodo.json, Zenodo reads CITATION.cff, so two rules check it. `zenodo-license-list` is an error for a `license` list, which Zenodo refuses. `zenodo-drops-field` warns about `identifiers` and `references`, which Zenodo leaves out of the record; a Zenodo DOI among the identifiers is fine.
- A keyword that differs from another file's only in hyphens, underscores or spaces is named in the finding, as in `industrial-ecology (CITATION.cff has 'industrial ecology': differs only in separators)`. `citesync write` gives it the source's spelling where it stands, instead of dropping it.
- `keywords-ignore-separators = true` treats such keywords as equal. Against Cargo.toml they always are, since crates.io refuses a keyword with a space.

### Changed

- **Breaking:** `codemeta-version` has no default. Unset, any CodeMeta version citesync reads (2.0, 3.0, 3.1, 4.0) passes and `citesync write` leaves `@context` alone; in 0.1.0 anything but 3.0 was a `context-mismatch` error.
- **Breaking:** a citation file the `files` setting lists that doesn't exist is a `file-missing` error. 0.1.0 skipped it.
- The field mapping is vendored from codemeta-drift 0.2.0, which adds the contributor and release-date rows; it was 0.1.0.
- `citesync check` starts about a third faster: it no longer loads what only `write`, `--version` or `--json` need.

### Fixed

- `citesync write` writes a new CITATION.cff entity (an author with only `name`) to codemeta.json as an `Organization`; it was a `Person` with that name as `familyName`.
- When `citesync write` adds authors to a JSON list, the entries already there keep their layout; a list of one-line entries was rewritten with each entry over several lines.
- `python -m citesync` runs the command line, as `citesync` does. It failed with "No module named `citesync.__main__`".
- A blank value no longer hides the field's value in its next place: with CITATION.cff's `doi: ""`, the DOI under `identifiers` was never read, so a different DOI in codemeta.json passed.
- codemeta.json entries written with `type` and `id`, which CodeMeta 3's context makes aliases of `@type` and `@id`, are read: a credit-matrix `Role` whose person is missing now gives `role-dangling`, and an `Organization` is written to CITATION.cff as an entity.
- Titles and descriptions compare in Unicode NFC, as names do. The same title typed with a composed and a decomposed accent was a `name-mismatch` whose two values looked identical.
- `citesync write` keeps a CITATION.cff author's `name-particle` and `name-suffix` when only the given name changes. It folded them into `family-names`.
- From a root in a subdirectory of the git repo, GitHub annotations name each file by its path in the repo, so they attach to the file.
- codemeta.json keywords given as one string are split on full-width (`，`) and ideographic (`、`) commas too.
- A pyproject.toml, Cargo.toml, package.json or .zenodo.json that starts with a byte order mark is `unreadable` with a message that says so, not the parser's.
- A file reached through a symlink that points out of the repo is `unreadable`: `check` no longer prints its fields and `write` no longer rewrites it. `write` won't create a file through a dangling link out of the repo either.
- Control characters in a file, such as an escape sequence in a keyword, are printed as `\xNN` in text and GitHub output, so they can't retitle the terminal or hide lines.
- On a stdout that isn't UTF-8, such as a Windows pipe, findings print as UTF-8; a CJK title made the check crash with exit 1.
- Input that could take minutes now takes well under a second: an npm or Cargo author string with a long run of spaces, an ORCID with one inside it, a CITATION.cff licence or DOI list that nests YAML aliases, and keyword lists thousands long.

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

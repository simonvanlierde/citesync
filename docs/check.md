# How `citesync check` works

`citesync check` compares ten fields with one file, the source (CITATION.cff by default): title/name, version, authors and contributors with ORCID, licence, DOI, repository URL, description, keywords and release date. When the source doesn't hold a field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

## Options

```sh
citesync check --source pyproject.toml  # pick another source file
citesync check --root path/to/repo      # check another directory
citesync check --format json            # or --json; also github and sarif, see output.md
citesync check -v                       # also list the fields that weren't compared (not-checked)
citesync check -q                       # only errors, no summary line
citesync rules                          # every rule and its severity; --format json too
```

## Which files it reads

By default it reads every citation file present, and the package manifests at the repo root. It skips a pyproject.toml without `[build-system]`, a private package.json, and any field in pyproject's `dynamic` list. It reads a Cargo workspace through `[workspace.package]`. [Configuration](config.md) changes the lists.

Run from a subdirectory, citesync walks up to the nearest directory with a citation file or a citesync config. It stops at the git root, so a submodule keeps its own files. File paths in findings are relative to that root.

A file citesync can't read or parse is an [`unreadable`](rules.md#unreadable) finding. The other files are still checked against each other.

## How values compare

citesync treats these spellings as equal:

- SPDX ids, SPDX URLs and Zenodo's lowercase ids. A licence list reads as `A OR B`.
- ORCID URLs and bare iDs.
- Zenodo's `"Family, Given"` and npm or Cargo `"Name <email>"`. CFF `name-particle` and `name-suffix` count as part of the family name.
- DOIs with or without `https://doi.org/`, and a DOI in a codemeta.json PropertyValue.
- Repository URLs, read as npm's hosted-git-info reads them: with or without `git+`, `.git`, `http://` or `www.`, as npm shorthands (`github:owner/repo`) or SSH remotes. A branch, tag or file page on GitHub, GitLab, Codeberg, Gitea or Bitbucket names its repository, as in `…/tree/v1.0`. Host names, and GitHub paths, compare in any case.
- PEP 621 url labels, normalised as packaging does (`Source Code`, `homepage`).
- PEP 440 versions: `v1.2.3` = `1.2.3`, `1.0` = `1.0.0`, `0.3.1-rc.1` = `0.3.1rc1`, `1.0.0-dev.1` = `1.0.0.dev1`. A version that isn't PEP 440 (`unreleased`) must match exactly.

Names and keywords compare case-insensitively. Titles and descriptions compare as written. All of them compare with whitespace collapsed and Unicode in NFC. Findings show each file's own spelling. Two config keys change how keywords compare:

- `keywords-case-sensitive = true` compares keywords by case too.
- `keywords-ignore-separators = true` treats `big-data`, `big_data` and `big data` as equal. Without it, the finding names such a keyword as a near miss, and write gives it the source's spelling.

Manifests are compared on version, authors' names (and npm contributors' names), licence, repository URL and keywords. They aren't compared on name or description. npm's one `author` is compared with the first author.

## Findings and exit codes

Each finding is one line, `file: severity[rule] field: message`. A last line counts them:

```text
.zenodo.json:2:1: error[unreadable] Expecting property name enclosed in double quotes
codemeta.json: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'
2 errors, 0 warnings in 3 files
```

On a terminal the severity is in colour. `NO_COLOR` turns colour off. `FORCE_COLOR` turns it on anywhere, and `FORCE_COLOR=0` or `false` turns it off. `NO_COLOR` wins.

[rules.md](rules.md) lists every rule id, its severity and how to fix it.

| Exit | When |
| ---: | --- |
| 0 | no error finding: warnings and info don't fail a run |
| 1 | an error finding, an unreadable file included |
| 2 | citesync couldn't run: a bad config or option, a missing source file, or an internal error. stdout is empty and stderr says why (a bad option prints the usage first) |

The JSON, GitHub and SARIF formats are in [output.md](output.md).

# How `citesync check` works

`citesync check` compares eleven fields with one file, the source (CITATION.cff by default): title/name, version, authors and contributors with ORCID, licence, DOI, Software Heritage identifier (SWHID), repository URL, description, keywords and release date. When the source doesn't hold a field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

## Options

```sh
citesync check --source pyproject.toml  # pick another source file
citesync check --root path/to/repo      # check another directory
citesync check --format json            # or --json; also github and sarif, see output.md
citesync check -v                       # also list the fields not compared and the manifests left out
citesync check -q                       # only errors, no summary line
citesync check --color never            # or always; the default, auto, colours on a terminal
citesync rules                          # every rule and its severity; --format json too
```

## Which files it reads

By default it reads every citation file present, and the package manifests at the repo root. It skips a pyproject.toml without `[build-system]`, a private package.json, and any field in pyproject's `dynamic` list. `-v` names each manifest it skipped and why ([`manifest-skipped`](rules.md#manifest-skipped)). It reads a Cargo workspace through `[workspace.package]`. [Configuration](config.md) changes the lists.

Run from a subdirectory, citesync walks up to the nearest directory with a citation file or a citesync config. It stops at the git root, so a submodule keeps its own files, and uses the git root when it found neither. File paths in findings are relative to that root. `citesync config` prints the root in use. `--root` must be a directory.

A file citesync can't read or parse is an [`unreadable`](rules.md#unreadable) finding. The other files are still checked against each other.

## How values compare

citesync treats these spellings as equal:

- SPDX ids, SPDX URLs and Zenodo's lowercase ids. A licence list reads as `A OR B`.
- ORCID URLs and bare iDs.
- Zenodo's `"Family, Given"` and npm or Cargo `"Name <email>"`. CFF `name-particle` and `name-suffix` count as part of the family name. A name in one string, such as codemeta `name` or npm `author`, also matches given and family names written family name first, as in `Tu Youyou` or `屠呦呦`. Two split names must have the same parts.
- DOIs with or without `https://doi.org/`, and a DOI in a codemeta.json PropertyValue.
- SWHIDs in any case of the hash. CFF reads the `identifiers` entry of type `swh`, .zenodo.json the `related_identifiers` entry with scheme `swh`, and codemeta.json a SWHID in `identifier`, as a string or a PropertyValue beside the DOI.
- Repository URLs, read as npm's hosted-git-info reads them: with or without `git+`, `.git`, `http://` or `www.`, as npm shorthands (`github:owner/repo`) or SSH remotes. A branch, tag or file page on GitHub, GitLab, Codeberg, Gitea or Bitbucket names its repository, as in `…/tree/v1.0`. Host names, and GitHub paths, compare in any case.
- PEP 621 url labels, normalised as packaging does (`Source Code`, `homepage`).
- PEP 440 versions: `v1.2.3` = `1.2.3`, `1.0` = `1.0.0`, `0.3.1-rc.1` = `0.3.1rc1`, `1.0.0-dev.1` = `1.0.0.dev1`. A version that isn't PEP 440 (`unreleased`) must match exactly.

Names and keywords compare case-insensitively. Titles and descriptions compare as written. All of them compare with whitespace collapsed and Unicode in NFC. Findings show each file's own spelling. Two config keys change how keywords compare:

- `keywords-case-sensitive = true` compares keywords by case too.
- `keywords-ignore-separators = true` treats `big-data`, `big_data` and `big data` as equal. Without it, the finding names such a keyword as a near miss, and write gives it the source's spelling.

Manifests are compared on version, authors' names (and npm contributors' names), licence, repository URL and keywords. They aren't compared on name or description. npm's one `author` is compared with the first author.

## Findings and exit codes

Each finding is a line, `file:line:column: severity[rule] field: message`, with a `help:` line under it that says what to do. The line and column point at the key the finding is about; a finding with no such key, such as a file citesync can't read at all, names the file alone. A line after the findings counts them. When check fails, a last line counts the errors `citesync write` would fix:

```text
.zenodo.json:2:1: error[unreadable] Expecting property name enclosed in double quotes
  help: Fix the file so its parser accepts it.
codemeta.json:3:3: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'
  help: Make the file agree with the source, or the other way round if the source is wrong.
2 errors, 0 warnings in 3 files
1 fixable with `citesync write`
```

A keyword finding between citation files names the words that are missing and extra, not both lists.

On a terminal the severity is in colour. `NO_COLOR` turns colour off. `FORCE_COLOR` turns it on anywhere, and `FORCE_COLOR=0` or `false` turns it off. `NO_COLOR` wins. `--color always` or `never` wins over both.

A config error names the bad entry first and suggests the closest valid one. An `ignore` entry that matched no finding prints a warning to stderr, unless you pass `-q`.

`citesync rules` lists every rule id and its severity. [rules.md](rules.md) says how to fix each one.

| Exit | When |
| ---: | --- |
| 0 | no error finding: warnings and info don't fail a run |
| 1 | an error finding, an unreadable file included |
| 2 | citesync couldn't run: a bad config or option, a missing source file, or an internal error. stdout is empty and stderr says why (a bad option prints the usage first). A missing source names the root it looked in |

The JSON, GitHub and SARIF formats are in [output.md](output.md).

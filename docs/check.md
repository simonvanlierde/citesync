# How `citesync check` works

`citesync check` compares ten fields with one file, the source (CITATION.cff by default): title/name, version, authors and contributors with ORCID, licence, DOI, repository URL, description, keywords and release date. When the source has no place or no value for a field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

## Which files it reads

By default it reads every citation file present and the release manifests at the repo root: a pyproject.toml without `[build-system]` and a private package.json are skipped, a field in pyproject's `dynamic` is skipped on its own, and a Cargo workspace is read through `[workspace.package]`. [Configuration](config.md) changes the lists. The tests run each of the six files as the source against a fixture where all six agree, and CITATION.cff as the source against [five real repositories](tested-repositories.md).

Run from a subdirectory, citesync finds the repo root as ruff does: it walks up to the nearest directory with a citation file or a citesync config, and stops at the git root, so a submodule keeps its own files. File paths in findings are relative to that root.

A file citesync can't read or parse is an `unreadable` finding, with the parser's message and its line and column when the parser gives them. The other files are still checked against each other, and when the unreadable file is the source, each field it holds is reported as `not-checked`.

## How values compare

Spellings are normalised before comparing:

- SPDX ids, SPDX URLs and Zenodo's lowercase ids. A licence list reads as `A OR B`.
- ORCID URLs and bare iDs.
- Zenodo's `"Family, Given"` and npm or Cargo `"Name <email>"`. CFF `name-particle` and `name-suffix` read as part of the family name.
- DOIs with or without `https://doi.org/`, and a codemeta `identifier` given as a schema.org PropertyValue (`propertyID` `DOI`, or a DOI as its `value` or `url`; other PropertyValues, such as a SWHID, are skipped).
- Repository URLs as npm's hosted-git-info reads them: `git+`, `.git`, `http://`, `www.`, the host's case, npm shorthands (`github:owner/repo`, `owner/repo`), SSH remotes, and a branch, tag or file page on GitHub, GitLab, Codeberg, Gitea or Bitbucket (`…/tree/v1.0`, as Zenodo's GitHub integration writes), with GitHub paths in any case.
- PEP 621 url labels as packaging normalises them (`Source Code`, `homepage`).
- Versions as PEP 440 versions (`v1.2.3` = `1.2.3`, `1.0` = `1.0.0`, `0.3.1-rc.1` = `0.3.1rc1`, `1.0.0-dev.1` = `1.0.0.dev1`). A version that isn't one (`unreleased`) must match exactly.

Names and keywords compare case-insensitively, with whitespace collapsed and Unicode in NFC; set `keywords-case-sensitive = true` to compare keywords by case too. A keyword that differs from another file's only in separators (`big-data`, `big_data`, `big data`) is named as a near miss in the finding, and write gives it the source's spelling where it stands; set `keywords-ignore-separators = true` to treat such keywords as equal. Findings show each file's own spelling.

Manifests are compared on version, authors' names, licence, repository URL and keywords, not on name or description. npm's one `author` is compared with the first author.

## Findings and exit codes

Each finding is one line, `file: severity[rule] field: message`, and a last line counts them:

```text
.zenodo.json:2:1: error[unreadable] Expecting property name enclosed in double quotes
codemeta.json: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'
2 errors, 0 warnings in 3 files
```

The severity is in colour on a terminal. `NO_COLOR` turns colour off, and `FORCE_COLOR` turns it on anywhere (`FORCE_COLOR=0` or `false` turns it off). `NO_COLOR` wins.

The rule ids name the field: `name-mismatch`, `version-mismatch`, `author-mismatch`, `contributor-mismatch`, `license-mismatch`, `doi-mismatch`, `repository-mismatch`, `description-mismatch`, `keywords-mismatch` and `date-mismatch` when a field differs from the source; `keywords-not-subset` for a manifest keyword the citation file doesn't have; `context-mismatch` when codemeta.json's `@context` isn't the configured CodeMeta version; `role-dangling` (warning) for a CodeMeta Role in codemeta.json whose person, named by ORCID, isn't listed; `version-behind-tag` (warning) when the source's version is older than the newest git tag; `zenodo-license-list` and `zenodo-drops-field` (warning) for what Zenodo can't take from a CITATION.cff alone; `file-missing` for a file `files` lists that doesn't exist; `unreadable` for a file citesync can't read; and `not-checked` (info) for a field that wasn't compared. [rules.md](rules.md) explains each one.

| Exit | When |
| ---: | --- |
| 0 | no error finding |
| 1 | an error finding, an unreadable file included |
| 2 | citesync couldn't run: a bad config or option, a missing source file, or an internal error. stdout is empty and stderr has one `citesync: <message>` line |

The JSON and GitHub formats are in [output.md](output.md).

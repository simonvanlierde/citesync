# citesync

[![python](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml)
[![PyPI](https://img.shields.io/pypi/v/citesync)](https://pypi.org/project/citesync/)
[![Python versions](https://img.shields.io/pypi/pyversions/citesync)](https://pypi.org/project/citesync/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/simonvanlierde/citesync/badge)](https://scorecard.dev/viewer/?uri=github.com/simonvanlierde/citesync)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/simonvanlierde/citesync/blob/main/LICENSE)

Status: experimental. It may change in ways that break your code, without notice.

Questions and bugs: see [CONTRIBUTING.md](https://github.com/simonvanlierde/citesync/blob/main/.github/CONTRIBUTING.md).

Software citation metadata: citesync checks that CITATION.cff, codemeta.json, .zenodo.json and the package manifests (pyproject.toml, Cargo.toml, package.json) say the same thing. Where each field sits in each file comes from a mapping of CodeMeta's crosswalks, exported by [codemeta-drift](https://github.com/simonvanlierde/codemeta-drift).

## What works now

`citesync check` compares eight fields with one file, the source (CITATION.cff by default): title/name, version, authors with ORCID, licence, DOI, repository URL, description and keywords.

```sh
uv tool install citesync            # or run it once with uvx citesync check
citesync check                      # exit 0: they agree; 1: an error finding; 2: citesync couldn't run
citesync check --source pyproject.toml
citesync check --root path/to/repo  # check another directory
citesync check --format json        # or --json; also --format github for workflow annotations
citesync check -v                   # also list fields that weren't compared (not-checked)
citesync check -q                   # only errors, no summary line
citesync rules                      # the rules, with their severity; --format json too
citesync explain version-mismatch   # what a rule checks and how to fix it
citesync config                     # the config in use, and the file it came from
citesync write                      # rewrite the other files to agree with the source
citesync write --diff               # print what write would change, and change nothing
citesync --version
```

Each finding is one line, `file: severity[rule] field: message`, and a last line counts them:

```text
.zenodo.json:2:1: error[unreadable] Expecting property name enclosed in double quotes
codemeta.json: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'
2 errors, 0 warnings in 3 files
```

The severity is in colour on a terminal. `NO_COLOR` turns colour off, and `FORCE_COLOR` turns it on anywhere (`FORCE_COLOR=0` or `false` turns it off). `NO_COLOR` wins.

The rule ids name the field: `name-mismatch`, `version-mismatch`, `author-mismatch`, `license-mismatch`, `doi-mismatch`, `repository-mismatch`, `description-mismatch` and `keywords-mismatch` when a field differs from the source; `keywords-not-subset` for a manifest keyword the citation file doesn't have; `context-mismatch` when codemeta.json's `@context` isn't the configured CodeMeta version; `role-dangling` (warning) for a CodeMeta Role in codemeta.json whose person, named by ORCID, isn't listed; `unreadable` for a file citesync can't read; and `not-checked` (info) for a field that wasn't compared. [docs/rules.md](https://github.com/simonvanlierde/citesync/blob/main/docs/rules.md) explains each one. When the source has no place or no value for a field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

A file citesync can't read or parse is an `unreadable` finding, with the parser's message and its line and column when the parser gives them. The other files are still checked against each other, and when the unreadable file is the source, each field it holds is reported as `not-checked`.

| Exit | When |
| ---: | --- |
| 0 | no error finding |
| 1 | an error finding, an unreadable file included |
| 2 | citesync couldn't run: a bad config or option, a missing source file, or an internal error. stdout is empty and stderr has one `citesync: <message>` line |

`--format json` prints one document:

```json
{
  "version": 1,
  "tool": { "name": "citesync", "version": "0.1.0" },
  "summary": { "files": 3, "errors": 1, "warnings": 0, "info": 0 },
  "findings": [
    {
      "rule": "version-mismatch",
      "severity": "error",
      "file": "codemeta.json",
      "term": "version",
      "message": "'2.0.0', CITATION.cff has '1.0.0'",
      "help": "Make the file agree with the source, or the other way round if the source is wrong.",
      "url": "https://github.com/simonvanlierde/citesync/blob/main/docs/rules.md#version-mismatch",
      "line": null,
      "column": null
    }
  ]
}
```

Findings are sorted by file, rule and field, and positions count from 1. A value longer than 80 characters is cut to 77 and ends in `...` in the message. `file` is null for a field no file holds, and `term` (the CodeMeta term) is null for `unreadable`. JSON always lists every finding: `-q` and `-v` change only the text and GitHub output. [tests/output.schema.json](https://github.com/simonvanlierde/citesync/blob/main/tests/output.schema.json) is the JSON Schema. A minor release may add rule ids and optional fields; ignore what you don't know. Removing or retyping a field bumps `version`, in a major release. `--format github` writes one workflow annotation per finding, titled `citesync <rule>`, and ends with a notice that counts them all, since GitHub shows only the first ten of each level.

Spellings are normalised before comparing: SPDX ids, SPDX URLs and Zenodo's lowercase ids; ORCID URLs and bare iDs; Zenodo's `"Family, Given"` and npm or Cargo `"Name <email>"`; DOIs with or without `https://doi.org/`, and a codemeta `identifier` given as a schema.org PropertyValue (`propertyID` `DOI`, or a DOI as its `value` or `url`; other PropertyValues, such as a SWHID, are skipped); repository URLs as npm's hosted-git-info reads them: `git+`, `.git`, `http://`, `www.`, the host's case, npm shorthands (`github:owner/repo`, `owner/repo`), SSH remotes, and a branch, tag or file page on GitHub, GitLab, Codeberg, Gitea or Bitbucket (`…/tree/v1.0`, as Zenodo's GitHub integration writes), with GitHub paths in any case; CFF `name-particle` and `name-suffix`, read as part of the family name; a licence list, read as `A OR B`; PEP 621 url labels as packaging normalises them (`Source Code`, `homepage`); versions as PEP 440 versions (`v1.2.3` = `1.2.3`, `1.0` = `1.0.0`, `0.3.1-rc.1` = `0.3.1rc1`, `1.0.0-dev.1` = `1.0.0.dev1`), while a version that isn't one (`unreleased`) must match exactly. Names and keywords compare case-insensitively, with whitespace collapsed and Unicode in NFC; set `keywords-case-sensitive = true` to compare keywords by case too. Findings show each file's own spelling. Manifests are compared on version, authors' names, licence, repository URL and keywords, not on name or description. npm's one `author` is compared with the first author.

By default it reads every citation file present and the release manifests at the repo root: a pyproject.toml without `[build-system]` and a private package.json are skipped, a field in pyproject's `dynamic` is skipped on its own, and a Cargo workspace is read through `[workspace.package]`. The tests run each of the six files as the source against a fixture where all six agree, and CITATION.cff as the source against five real repositories.

`citesync write` fixes what `check` reports, and nothing more. `citesync write --diff` prints the same edits as a unified diff and writes nothing; it exits 1 when there is a change, or a file it can't read (listed on stderr), so CI can run it. It writes every citation file that isn't the source, and a manifest only for the fields listed in `write-manifests` (or all of them with `"all"`). A field a file leaves out stays out: a .zenodo.json without a version never gains one. When the source has no value for a field (no DOI in pyproject.toml), write leaves that field alone in the other files. It keeps each file's layout: comments, key order and quoting in CITATION.cff, comments in TOML, and in JSON the key order, indentation, one-line arrays and final newline. Each value is spelled the way that file spells it (Zenodo's `"Family, Given"` and lowercase licence ids, a DOI URL in codemeta.json, where a schema.org PropertyValue keeps its other keys, semver in Cargo.toml and package.json, PEP 440 in pyproject.toml). A value the file can't spell is left as it was, and its finding says why: a compound licence in .zenodo.json, a licence with `AND` or `WITH` in CITATION.cff or codemeta.json (`OR` becomes a list), in Cargo.toml and package.json a version semver has no spelling for (a post-release such as `1.2.3.post1`, an epoch, more than three numbers), and in pyproject.toml a version that isn't PEP 440. An author with only a name, such as an organization (`name` in CITATION.cff and codemeta.json), counts as a family name and keeps it. An author whose name or ORCID matches keeps the rest of their entry, such as an email or affiliation; anyone else gets a new entry. When that would drop an old entry holding more than a name and ORCID, such as after a renaming in a manifest, write leaves that file's authors for you to edit. A Cargo field inherited with `.workspace = true` is left as it is: change it in the workspace's `[workspace.package]`.

Values that compare equal stay as written: write leaves `v1.2.3` against `1.2.3`, and `LCA` against `lca` unless `keywords-case-sensitive` is set. A finding whose rule `ignore` lists is not written, and an `unreadable` file is never written. It prints `wrote <file>` for each file it changed (to stderr with `--format json` or `github`, and not at all with `--quiet`), then reports the findings left as `check` does, in the same formats, each with what to do: edit it by hand (with the reason, when write could have written it but didn't), or add the field to `write-manifests`. Exit 0 when no error finding remains, 1 when one does (an unreadable file included), and 2 when citesync couldn't run. Every file is written to a temporary file beside it before any is moved into place, so a failure leaves the files as they were, unless a move itself fails, which leaves the files moved before it written. A symlinked file is written through the link, CRLF line ends stay CRLF, and a file that would not change is not touched.

Known limits of the CITATION.cff round trip: an end-of-line comment aligned with spaces after a value (`title:    x   # c`) is reflowed, a second sequence indented differently from the first is reindented to match it, and a closing `...` and a byte-order mark are dropped.

Config goes in the first of `citesync.toml`, `.citesync.toml`, `[tool.citesync]` in pyproject.toml, `[workspace.metadata.citesync]` or `[package.metadata.citesync]` in Cargo.toml, or `"citesync"` in package.json:

```toml
source = "CITATION.cff"                  # any of the six files
codemeta-version = "3.0"
files = ["codemeta.json", ".zenodo.json"]  # default: the citation files present
manifests = ["src/core/package.json"]      # replaces the default root manifests
write-manifests = ["keywords", "license"]  # or "all"; the manifest fields write may change
keywords-case-sensitive = true              # default false: keywords compare as names do
ignore = ["description-mismatch"]          # rule ids whose findings to drop
```

`write-manifests` names fields by their CodeMeta term, as the JSON `term` does: `name`, `version`, `author`, `license`, `identifier` (the DOI), `codeRepository`, `description` and `keywords`. Rule ids use the plainer `doi` and `repository`.

An `ignore` entry that matched no finding prints a warning to stderr. An unknown rule id is a config error, and `unreadable` can't be ignored.

Not built yet: creating a citation file listed under `files` that doesn't exist yet.

## Pre-commit hook

For [prek](https://prek.j178.dev) or [pre-commit](https://pre-commit.com), in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/simonvanlierde/citesync
    rev: v0.1.0
    hooks:
      - id: citesync
      - id: citesync-write
```

The hook runs `citesync check` from the repo root when a commit changes CITATION.cff, codemeta.json, .zenodo.json, pyproject.toml, Cargo.toml, package.json, `citesync.toml` or `.citesync.toml`, at any depth. It always checks every file, not only the staged ones, and fails the commit on an error finding. `citesync-write` runs `citesync write` only when you ask for it: `prek run citesync-write --stage manual --all-files`.

## Tested on real repositories

The tests copy the metadata files of five public repositories byte for byte (commits in [tests/fixtures/SOURCES.txt](https://github.com/simonvanlierde/citesync/blob/main/tests/fixtures/SOURCES.txt)) and check that citesync reports exactly these findings, with CITATION.cff as the source.

| Repository | Config | Findings | Exit | Why |
| --- | --- | --- | ---: | --- |
| sourceledger | none | codemeta.json `context-mismatch` | 1 | codemeta.json uses the CodeMeta 4.0 context, and citesync expects 3.0 unless `codemeta-version` says otherwise. pyproject.toml and .zenodo.json agree on every field |
| credit-matrix | none | codemeta.json `name-mismatch` | 1 | codemeta.json names it "CRediT Matrix", CITATION.cff "CRediT Matrix: drafting CRediT contribution statements with co-authors". The root package.json is private, so it is skipped |
| credit-matrix | `manifests = ["src/core/package.json"]` | codemeta.json `name-mismatch` | 1 | As above. The package agrees: its version, licence and author match, its keywords are a subset, and its `git+…/credit-matrix.git` repository names the same repository |
| jsonvet | none | Cargo.toml `keywords-not-subset` | 1 | The workspace keywords include `lint`, and CITATION.cff has `linter`. Only Cargo.toml holds a version, so there is nothing to compare it with |
| jsonvet | `manifests = ["crates/jsonvet-cli/pyproject.toml"]` | that pyproject.toml `keywords-not-subset`; `not-checked` version (info) | 1 | The same keyword. The list replaces the root manifests and the pyproject version is `dynamic`, so no file holds a version |
| r9lab | none | codemeta.json `context-mismatch` | 1 | As sourceledger. The root pyproject.toml has no `[build-system]` and the root package.json is private, so no manifest is checked |
| project-templates | none | `not-checked` version (info) | 0 | CITATION.cff alone, with no version |

A made-up set where all six files agree exits 0 with each of them as the source.

## Development

You need [uv](https://docs.astral.sh/uv/) and [just](https://just.systems).

```sh
uv sync
uv tool install prek   # once per machine
prek install     # git hooks
```

`just` lists the tasks. They mirror what [.github/workflows/](https://github.com/simonvanlierde/citesync/tree/main/.github/workflows) runs.

```sh
just check       # lint, types and tests for every stack here
just fmt         # apply each stack's fixes and formatting
just hooks       # the git hooks, as the checks workflow runs them
just mutation    # mutation-test the comparison code (not in CI)
```

`just mutation` changes `check.py` and `codecs.py` one small step at a time and fails if the tests
still pass on a change that `tests/mutation-baseline.txt` does not list. A change that
cannot alter behaviour goes in that file with the reason. It also fails on a listed
change the tests now catch, so the list stays true.

uv locks only releases at least a week old. If `just check` fails on
a security fix newer than that, add the package to `exclude-newer-package` under `[tool.uv]` in `pyproject.toml`,
and remove it a week later ([how](https://github.com/simonvanlierde/project-templates/blob/main/docs/tooling.md#dependencies)).

## Releasing

To release, add a `## [X.Y.Z]` section to `CHANGELOG.md`, then push the tag `vX.Y.Z`.
`python-release.yml` publishes to PyPI, then creates the GitHub release with the distributions and their provenance bundle.
Approve the `pypi` environment when prompted. Do not create the GitHub release by hand.
If the release job fails after PyPI succeeds, delete any leftover draft with `gh release delete vX.Y.Z`.
Re-run only the `release` job. A published immutable release needs a new patch version to fix its files.

Before the first release, set up the publishing environment
(`pypi`)
in Settings > Environments: limit it to tags matching `v*`, and add a required reviewer.
The release workflows explain the rest in their header comments.

## License

See [LICENSE](https://github.com/simonvanlierde/citesync/blob/main/LICENSE) for the license terms.

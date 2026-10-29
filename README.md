# citesync

[![python](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml)
[![PyPI](https://img.shields.io/pypi/v/citesync)](https://pypi.org/project/citesync/)
[![Python versions](https://img.shields.io/pypi/pyversions/citesync)](https://pypi.org/project/citesync/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/simonvanlierde/citesync/badge)](https://scorecard.dev/viewer/?uri=github.com/simonvanlierde/citesync)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

Status: experimental. It may change in ways that break your code, without notice.

Questions and bugs: see [CONTRIBUTING.md](.github/CONTRIBUTING.md).

Software citation metadata: citesync checks that CITATION.cff, codemeta.json, .zenodo.json and the package manifests (pyproject.toml, Cargo.toml, package.json) say the same thing. Where each field sits in each file comes from a mapping of CodeMeta's crosswalks, exported by [codemeta-drift](https://github.com/simonvanlierde/codemeta-drift).

## What works now

`citesync check` compares eight fields with one file, the source (CITATION.cff by default): title/name, version, authors with ORCID, licence, DOI, repository URL, description and keywords. It is silent when the files agree.

```sh
citesync check                      # exit 0: they agree; 1: findings; 2: couldn't check
citesync check --source pyproject.toml
citesync check --format json        # or --json; also --format github for workflow annotations
citesync check -v                   # also list fields no file holds (NOT_CHECKED)
citesync config                     # the config in use, and the file it came from
```

Each finding is one line, `CODE file: field: detail`:

- `MISMATCH`: a field differs from the source. When the source has no place or no value for a field (pyproject.toml has no DOI), the other files that hold it must agree with each other.
- `NOT_SUBSET`: a manifest keyword the citation file doesn't have. A manifest's keywords must be a subset of the citation file's (crates.io allows five).
- `CONTEXT`: codemeta.json's `@context` is not the configured CodeMeta version (3.0 by default).

Spellings are normalised before comparing: SPDX ids, SPDX URLs and Zenodo's lowercase ids; ORCID URLs and bare iDs; Zenodo's `"Family, Given"` and npm or Cargo `"Name <email>"`; DOIs with or without `https://doi.org/`, and a codemeta `identifier` given as a schema.org PropertyValue (`propertyID` `DOI`, or a DOI as its `value` or `url`; other PropertyValues, such as a SWHID, are skipped); repository URLs as npm's hosted-git-info reads them: `git+`, `.git`, `http://`, `www.`, the host's case, npm shorthands (`github:owner/repo`, `owner/repo`), SSH remotes, and a branch, tag or file page on GitHub, GitLab, Codeberg, Gitea or Bitbucket (`…/tree/v1.0`, as Zenodo's GitHub integration writes), with GitHub paths in any case; CFF `name-particle` and `name-suffix`, read as part of the family name; a licence list, read as `A OR B`; PEP 621 url labels as packaging normalises them (`Source Code`, `homepage`); versions as PEP 440 versions (`v1.2.3` = `1.2.3`, `1.0` = `1.0.0`, `0.3.1-rc.1` = `0.3.1rc1`, `1.0.0-dev.1` = `1.0.0.dev1`), while a version that isn't one (`unreleased`) must match exactly. Names and keywords compare case-insensitively, with whitespace collapsed and Unicode in NFC; set `keywords_case_sensitive = true` to compare keywords by case too. Findings show each file's own spelling. Manifests are compared on version, authors' names, licence, repository URL and keywords, not on name or description. npm's one `author` is compared with the first author.

By default it reads every citation file present and the release manifests at the repo root: a pyproject.toml without `[build-system]` and a private package.json are skipped, a field in pyproject's `dynamic` is skipped on its own, and a Cargo workspace is read through `[workspace.package]`. The tests run each of the six files as the source against a fixture where all six agree, and CITATION.cff as the source against five real repositories.

Config goes in the first of `citesync.toml`, `.citesync.toml`, `[tool.citesync]` in pyproject.toml, `[workspace.metadata.citesync]` or `[package.metadata.citesync]` in Cargo.toml, or `"citesync"` in package.json:

```toml
source = "CITATION.cff"                  # any of the six files
codemeta_version = "3.0"
files = ["codemeta.json", ".zenodo.json"]  # default: the citation files present
manifests = ["src/core/package.json"]      # replaces the default root manifests
write_manifests = ["keywords", "license"]  # or "all"; for write, not built yet
keywords_case_sensitive = true              # default false: keywords compare as names do
```

Not built yet: `citesync write`, which exits 2 in this build, the `diff` format, and the pre-commit hook.

## Development

You need [uv](https://docs.astral.sh/uv/) and [just](https://just.systems).

```sh
uv sync
uv tool install prek   # once per machine
prek install     # git hooks
```

`just` lists the tasks. They mirror what [.github/workflows/](.github/workflows/) runs.

```sh
just check       # lint, types and tests for every stack here
just fmt         # apply each stack's fixes and formatting
just hooks       # the git hooks, as the checks workflow runs them
```

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

See [LICENSE](LICENSE) for the license terms.

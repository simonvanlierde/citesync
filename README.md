# citesync

[![python](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml)
[![PyPI](https://img.shields.io/pypi/v/citesync)](https://pypi.org/project/citesync/)
[![Python versions](https://img.shields.io/pypi/pyversions/citesync)](https://pypi.org/project/citesync/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/simonvanlierde/citesync/badge)](https://scorecard.dev/viewer/?uri=github.com/simonvanlierde/citesync)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/simonvanlierde/citesync/blob/main/LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23779706.svg)](https://doi.org/10.5281/zenodo.23779706)

Status: experimental. It may change in ways that break your code, without notice.

Questions and bugs: see [CONTRIBUTING.md](https://github.com/simonvanlierde/citesync/blob/main/.github/CONTRIBUTING.md).

Software citation metadata: citesync checks that CITATION.cff, codemeta.json, .zenodo.json and the package manifests (pyproject.toml, Cargo.toml, package.json) say the same thing. Where each field sits in each file comes from a mapping of CodeMeta's crosswalks, exported by [codemeta-drift](https://github.com/simonvanlierde/codemeta-drift).

## What works now

`citesync check` compares eight fields with one file, the source (CITATION.cff by default): title/name, version, authors with ORCID, licence, DOI, repository URL, description and keywords. `citesync write` rewrites the other files to agree with it.

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

```text
codemeta.json: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'
1 error, 0 warnings in 3 files
```

More in `docs/`:

- [How check works](https://github.com/simonvanlierde/citesync/blob/main/docs/check.md): which files it reads, how spellings are normalised, findings and exit codes.
- [How write works](https://github.com/simonvanlierde/citesync/blob/main/docs/write.md): what it writes, how it keeps each file's layout, and its limits.
- [Rules](https://github.com/simonvanlierde/citesync/blob/main/docs/rules.md): each rule id, what it checks and how to fix it.
- [Configuration](https://github.com/simonvanlierde/citesync/blob/main/docs/config.md): where config goes and every key.
- [Output formats](https://github.com/simonvanlierde/citesync/blob/main/docs/output.md): the JSON document and GitHub annotations.
- [Tested on real repositories](https://github.com/simonvanlierde/citesync/blob/main/docs/tested-repositories.md): what citesync reports on five public repositories.

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
```

`just mutation`, which CI doesn't run, changes `check.py` and `codecs.py` one small step at a time and fails if the tests
still pass on a change that `tests/mutation-baseline.txt` does not list. A change that
cannot alter behaviour goes in that file with the reason. It also fails on a listed
change the tests now catch, so the list stays true.

uv locks only releases at least a week old. If `just check` fails on
a security fix newer than that, add the package to `exclude-newer-package` under `[tool.uv]` in `pyproject.toml`,
and remove it a week later ([how](https://github.com/simonvanlierde/project-templates/blob/main/docs/tooling.md#dependencies)).

## Releasing

See [docs/releasing.md](https://github.com/simonvanlierde/citesync/blob/main/docs/releasing.md).

## License

See [LICENSE](https://github.com/simonvanlierde/citesync/blob/main/LICENSE) for the license terms.

# citesync

[![python](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml/badge.svg)](https://github.com/simonvanlierde/citesync/actions/workflows/python.yml)
[![PyPI](https://img.shields.io/pypi/v/citesync)](https://pypi.org/project/citesync/)
[![Python versions](https://img.shields.io/pypi/pyversions/citesync)](https://pypi.org/project/citesync/)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/simonvanlierde/citesync/badge)](https://scorecard.dev/viewer/?uri=github.com/simonvanlierde/citesync)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/16151/badge)](https://www.bestpractices.dev/projects/16151)
[![license](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](https://github.com/simonvanlierde/citesync/blob/main/LICENSE)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23779706.svg)](https://doi.org/10.5281/zenodo.23779706)

Status: experimental. It may change in ways that break your code, without notice.

Questions and bugs: see [CONTRIBUTING.md](https://github.com/simonvanlierde/citesync/blob/main/.github/CONTRIBUTING.md).

Generate software citation files from package metadata, then keep them in sync across CITATION.cff, codemeta.json, .zenodo.json and package manifests, including [Typst and Quarto plugin manifests](docs/formats.md#plugin-manifests). Use the CLI, a pre-commit hook or the [browser playground](https://simonvanlierde.com/citesync/). Field mappings come from CodeMeta's crosswalks, as exported by [codemeta-drift](https://github.com/simonvanlierde/codemeta-drift).

## Usage

citesync compares eleven fields, from title to release date, with one file: the source. The source is CITATION.cff unless you pick another with `--source`. With neither, citesync exits 3. Use citesync through its command line and the pre-commit hook. Its Python modules are internal and may change in any release.

```sh
uv tool install citesync            # or run it once with uvx citesync check
citesync check                      # exit 0: no error finding; 1: an error finding; 2: usage error; 3: couldn't run
citesync check --source pyproject.toml
citesync write --diff               # print what write would change, and change nothing
citesync write                      # rewrite the other files to agree with the source
citesync init                       # write a CITATION.cff from codemeta.json, .zenodo.json and the manifests
citesync export --format apa        # print a citation: apa, bibtex, csl-json, jsonld, cff, codemeta or zenodo
citesync explain version-mismatch   # what a rule checks and how to fix it
citesync config                     # the config in use, and the file it came from
```

```text
codemeta.json:3:3: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'
  help: Make the file agree with the source, or the other way round if the source is wrong.
1 error, 0 warnings in 3 files
1 fixable with `citesync write`
```

A config is optional. A one-line `citesync.toml` is `ignore = ["description-mismatch"]`.

`citesync --help` lists every command and option. The reference is in `docs/`:

- [How check works](https://github.com/simonvanlierde/citesync/blob/main/docs/check.md): the fields, files, options and exit codes.
- [How write works](https://github.com/simonvanlierde/citesync/blob/main/docs/write.md): what it changes and what it leaves alone.
- [Supported files](https://github.com/simonvanlierde/citesync/blob/main/docs/formats.md): which files citesync reads, updates and creates, including read-only Python distribution, R and Julia metadata.
- [How init works](https://github.com/simonvanlierde/citesync/blob/main/docs/init.md): where a new CITATION.cff takes each field from.
- [Citation exports](https://github.com/simonvanlierde/citesync/blob/main/docs/export.md): BibTeX, CSL-JSON, APA and schema.org JSON-LD files kept in step with the source.
- [Rules](https://github.com/simonvanlierde/citesync/blob/main/docs/rules.md): each rule id, what it checks and how to fix it.
- [Configuration](https://github.com/simonvanlierde/citesync/blob/main/docs/config.md): where config goes, and every key.
- [Use citation exports with Pandoc](https://github.com/simonvanlierde/citesync/blob/main/docs/pandoc.md): cite software from the CSL-JSON or BibTeX files `citesync export` or the playground makes.
- [Output formats](https://github.com/simonvanlierde/citesync/blob/main/docs/output.md): JSON, GitHub annotations and SARIF.
- [Tested on real repositories](https://github.com/simonvanlierde/citesync/blob/main/docs/tested-repositories.md): what citesync reports on five public repositories.

## Browser playground

Generate citation files from existing metadata or basic project details, without installing Python. [Open the playground](https://simonvanlierde.com/citesync/) or [run it locally](https://github.com/simonvanlierde/citesync/blob/main/playground/README.md). Files are processed in the browser; downloading the converter requires a network connection.

## Pre-commit hook

For [prek](https://prek.j178.dev) or [pre-commit](https://pre-commit.com), in `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/simonvanlierde/citesync
    rev: v0.4.0
    hooks:
      - id: citesync
      - id: citesync-write
```

The `citesync` hook runs when a commit changes a supported metadata file, a citesync config or a file with an export suffix (`.bib`, `.csl.json`, `.apa.txt`, `.jsonld`), at any depth. It checks every file, not only the staged ones, and fails the commit on an error finding (exit 1) or when citesync can't run (exit 3), such as on a bad config. The [exit codes](https://github.com/simonvanlierde/citesync/blob/main/docs/check.md#findings-and-exit-codes) are the same as on the command line. The `citesync-write` hook runs only when you ask for it: `prek run citesync-write --stage manual --all-files`.

## Development

You need [uv](https://docs.astral.sh/uv/), [just](https://just.systems), Node.js 26 and [pnpm](https://pnpm.io/).

```sh
uv sync
pnpm install --frozen-lockfile
uv tool install prek   # once per machine
prek install           # git hooks
```

`just` lists the tasks. They mirror what [.github/workflows/](https://github.com/simonvanlierde/citesync/tree/main/.github/workflows) runs.

```sh
just check       # lint, types and tests for every stack here
just fmt         # apply each stack's fixes and formatting
just hooks       # the git hooks, as the checks workflow runs them
```

`just mutation` mutation-tests the modules `only_mutate` lists under `[tool.mutmut]` in `pyproject.toml`. CI doesn't run it. It fails when the tests miss a change that `tests/mutation-baseline.txt` doesn't list. A change that can't alter behaviour goes in that file, with the reason. It also fails when the tests now catch a listed change, so drop that line.

uv locks only releases at least a week old. If `just check` fails on a newer security fix, add the package to `exclude-newer-package` under `[tool.uv]` in `pyproject.toml`, and remove it a week later ([how](https://github.com/simonvanlierde/project-templates/blob/main/docs/tooling.md#dependencies)).

## Licence

See [LICENSE](https://github.com/simonvanlierde/citesync/blob/main/LICENSE).

# Getting started

Install citesync with [uv](https://docs.astral.sh/uv/), then run a first check from your repository:

```sh
uv tool install citesync
citesync check
```

Python 3.13 or newer is required. To run a check without installing citesync, use `uvx citesync check`.

## Create your citation file

If your repository has package metadata but no CITATION.cff, create one and review it:

```sh
citesync init
citesync check
```

[The init guide](init.md) explains where each field comes from. To work without Python, [use the browser playground](../playground/README.md) instead.

## Review and fix differences

A check compares the metadata files with CITATION.cff by default. Select another source explicitly when needed:

```sh
citesync check --source pyproject.toml
citesync write --diff
citesync write
```

Review the preview before writing. The [write guide](write.md) explains which files and fields can change. The [check guide](check.md) explains findings and exit codes.

## Add checks to your workflow

[Set up the pre-commit hook](../README.md#pre-commit-hook) for repeatable checks. [Require selected fields](config.md#require-values-in-selected-files) when a release needs authors, licences or a DOI. For data releases, [keep software and dataset metadata separate](datasets.md).

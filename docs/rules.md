# Rules

<!-- Generated from src/citesync/rules.py by `uv run python -m citesync.rules > docs/rules.md`. Edit that file, not this one. -->

`citesync rules` lists these rules, and `citesync explain <id>` prints one section.

## name-mismatch

The title differs from the source's. Severity: error.

CFF `title` and CodeMeta and Zenodo `name`/`title` compare as written, with whitespace collapsed. Manifests are not compared: a manifest `name` is a package id. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## version-mismatch

The version differs from the source's. Severity: error.

Semver pre-release tags are read as PEP 440 first, so `0.3.1-rc.1` equals `0.3.1rc1`. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## author-mismatch

The authors differ from the source's. Severity: error.

Citation files must list the same people in the same order, with equal ORCIDs where both have one. Names compare case-insensitively after Unicode normalisation, and Zenodo's `Family, Given` and npm or Cargo `Name <email>` are read as names. Manifests are compared on names only, and npm's one `author` with the first author. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## license-mismatch

The licence differs from the source's. Severity: error.

SPDX ids, SPDX URLs and Zenodo's lowercase ids are the same licence, compared case-insensitively. A list of licences reads as `A OR B`. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## doi-mismatch

The DOI differs from the source's. Severity: error.

DOIs compare case-insensitively, with or without `https://doi.org/`. Manifests have no DOI. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## repository-mismatch

The repository URL differs from the source's. Severity: error.

`git+`, `.git` and a trailing slash are removed first, and npm shorthands and SSH remotes are read as https URLs. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## description-mismatch

The description differs from the source's. Severity: error.

Compared as written, with whitespace collapsed. Manifests are not compared: a manifest description is a one-line summary, not an abstract. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## keywords-mismatch

The keywords differ from the source's. Severity: error.

Citation files must hold the same keywords, in any order. A manifest's keywords are checked by `keywords-not-subset` instead. When the source has no place or no value for the field (pyproject.toml has no DOI), the other files that hold it must agree with each other.

To fix: Make the file agree with the source, or the other way round if the source is wrong.

## keywords-not-subset

A manifest has a keyword the citation file doesn't. Severity: error.

A manifest's keywords must all be in the citation file's, whichever of the two is the source: a citation file can hold more keywords than a registry allows (crates.io allows five).

To fix: Add the keyword to the citation file, or remove it from the manifest.

## context-mismatch

codemeta.json's `@context` is not the configured CodeMeta version. Severity: error.

The configured version is `codemeta-version`, 3.0 by default. citesync reads CodeMeta 2.0, 3.0, 3.1 and 4.0.

To fix: Change the `@context` to the configured version, or set `codemeta-version` in the config.

## role-dangling

A CodeMeta Role in codemeta.json points at a person who isn't listed. Severity: warning.

A `Role` entry in codemeta.json's `author` or `contributor` list, as credit-matrix writes CRediT roles, names its person by ORCID in `schema:author`. The rule warns when no `Person` in either list has that ORCID as its `@id`, as after someone is replaced. The role itself is not checked, and `write` never changes a Role.

To fix: Add the person back, point the Role at their ORCID, or remove the Role.

## unreadable

citesync could not read the file. Severity: error.

The file could not be opened, is not UTF-8, does not parse, has a top level that is not a mapping, holds a value of a shape its format doesn't allow, or is a format version citesync doesn't read (CFF other than 1.2.0, a codemeta.json whose `@context` is not CodeMeta). The finding gives the parser's message, and its line and column when the parser reports them. The other files are still checked against each other. When the unreadable file is the source, each field it has a place for is reported as `not-checked`. This rule can't be ignored.

To fix: Fix the file so its parser accepts it.

## not-checked

A field was not compared. Severity: info.

Either no file holds a value for the field, or the source could not be read. Info only: it never changes the exit code, and text and GitHub output show it only with `--verbose`.

To fix: Add the field to the source if the files should carry it.

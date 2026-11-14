# Governance

citesync has one maintainer, Simon van Lierde. This page says who decides what, and
what happens if he is unavailable.

## Roles

- **Maintainer:** reviews and merges pull requests, triages issues, makes releases, and
  handles security reports. Only a maintainer can merge to `main` or publish to PyPI.
- **Contributor:** anyone who opens an issue or a pull request. [CONTRIBUTING.md](.github/CONTRIBUTING.md)
  says how.

## How decisions are made

The maintainer decides. A change that affects users, such as a new format, rule, CLI
flag or breaking change, starts as an issue, so anyone can comment before the code is
written. The reasons for major choices go in [docs/decisions/](docs/decisions/) or in
the issue or pull request, where anyone can read them later.

Three design boundaries hold unless a decision record revises them: field locations come
only from the pinned `codemeta-drift` mapping export, citesync stays vocabulary-blind
(CRediT roles are kept intact and never mapped to Zenodo contributor types), and `write`
updates existing fields rather than inventing missing ones.

## Python support

We support released CPython versions from 3.13 onward. Version drops follow
[Scientific Python SPEC 0](https://scientific-python.org/specs/spec-0000/) and are
recorded in the changelog as breaking changes.

## Releases

The maintainer runs `just release X.Y.Z` to push a signed `v*` tag on `main`. The
release workflow runs the full suite on the tagged commit, and again against the built
wheel, before it publishes to PyPI. The maintainer approves each publish by hand. The
workflow then creates the GitHub release, with the wheel, the sdist, a CycloneDX SBOM
and each file's signed provenance as assets, and checks every attestation before it
publishes the release. Each release has a section in [CHANGELOG.md](CHANGELOG.md), with
breaking changes marked and upgrade steps first.

## Adding a maintainer

An existing maintainer adds a new one, by name in this file and in
[CONTRIBUTING.md](.github/CONTRIBUTING.md#who-maintains-this). A new maintainer gets
write access to the repository and owner access to the PyPI project.

## If the maintainer is unavailable

A named person can take over the GitHub repository. The recovery details for PyPI and
Zenodo are in an emergency-access vault.

The code, the release history and the docs are public under the Apache-2.0 license, so
anyone can fork the project and publish it under another name. Installed copies keep
working without upkeep, and each release is pinned on PyPI.

## Changing this document

A change to this file is a pull request like any other, and the maintainer decides it.

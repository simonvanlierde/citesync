# Roadmap

Last reviewed: 2026-11-20

## Current release

Version 0.6.0 was published on 2026-11-16. Version 0.7.0 adds JSON output for more CLI commands and breaking changes to rules output and usage-error reporting.

Physical-device, Safari, real screen-reader and reference-manager checks remain unverified. Publication does not establish that these checks passed.

Dataset metadata and required-field checks are implemented, and the consuming repositories have adopted them. The playground includes form mode and field lookup. Documentation is searchable, and installation, playground and reference guides stay on this website. See the [release notes](../CHANGELOG.md) for the changes.

## After 0.6

- Submit citesync to the Research Software Directory after the release is published.

## Not planned

- Mapping CRediT roles to Zenodo contributor types: citesync stays vocabulary-blind ([decision 0005](decisions/0005-vocabulary-blind-roles.md)).
- Hand-written field locations outside the pinned `codemeta-drift` export ([decision 0002](decisions/0002-vendored-mapping.md)).
- Executing package code (`setup.py`, `Package.swift`, `gemspec`) to extract metadata.

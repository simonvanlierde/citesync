# Roadmap

Last reviewed: 2026-11-14

## Before 0.6

- Finish the release review and checks for dataset CodeMeta, required fields, playground form mode and field lookup.
- Complete physical-device, screen-reader and reference-manager checks before publication.

Dataset metadata and required-field checks are implemented, and the consuming repositories have adopted them. The playground includes form mode and field lookup. Documentation is searchable, and installation, playground and reference guides stay on this website. See the [release notes](../CHANGELOG.md) for the changes.

## After 0.6

- Submit citesync to the Research Software Directory after the release is published.

## Not planned

- Mapping CRediT roles to Zenodo contributor types: citesync stays vocabulary-blind ([decision 0005](decisions/0005-vocabulary-blind-roles.md)).
- Hand-written field locations outside the pinned `codemeta-drift` export ([decision 0002](decisions/0002-vendored-mapping.md)).
- Executing package code (`setup.py`, `Package.swift`, `gemspec`) to extract metadata.

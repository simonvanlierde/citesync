# Roadmap

Last reviewed: 2026-11-14

## Before 0.6

- Review and merge dataset CodeMeta writing and checking, including required-field checks and distinct software and dataset licences ([#108](https://github.com/simonvanlierde/citesync/pull/108)).
- Add field lookup beside the existing form mode and publish the guides on this website ([#109](https://github.com/simonvanlierde/citesync/pull/109)).
- Adopt the metadata checks in the repositories that consume citesync and complete the release checks.

## After 0.6

- Submit citesync to the Research Software Directory after the release is published.

## Not planned

- Mapping CRediT roles to Zenodo contributor types: citesync stays vocabulary-blind ([decision 0005](decisions/0005-vocabulary-blind-roles.md)).
- Hand-written field locations outside the pinned `codemeta-drift` export ([decision 0002](decisions/0002-vendored-mapping.md)).
- Executing package code (`setup.py`, `Package.swift`, `gemspec`) to extract metadata.

# Roadmap

Last reviewed 26 November 2026. This roadmap covers the next year, through November 2027.

## Current release

The [release notes](../CHANGELOG.md) describe published versions and upgrade steps. Version 0.7.0 is prepared on `main`. It adds Composer import and changes JSON rules output and usage-error reporting.

The remaining manual release checks are physical iPhone Safari, native EndNote import and screen-reader announcements for page controls.

## Planned through November 2027

- Publish 0.7.0 and submit citesync to the Research Software Directory.
- Add read-only Maven package metadata import using the pinned CodeMeta mapping.
- Recheck Software Heritage's support for CodeMeta 4.0 by April 2027. Use the newer context by default when the indexer supports it.
- Work through the [OpenSSF Silver criteria](https://www.bestpractices.dev/en/criteria/1) and maintain the evidence for dependency checks, tests and release verification.
- Run an outside pilot if a participating project volunteers. Publish an example from the pilot with the project's agreement.

## Not planned

- Mapping CRediT roles to Zenodo contributor types: citesync stays vocabulary-blind ([decision 0005](decisions/0005-vocabulary-blind-roles.md)).
- Hand-written field locations outside the pinned `codemeta-drift` export ([decision 0002](decisions/0002-vendored-mapping.md)).
- Executing package code (`setup.py`, `Package.swift`, `gemspec`) to extract metadata.

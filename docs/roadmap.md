# Roadmap

Last reviewed: 2026-11-26

## Current release

Version 0.6.0 was published on 2026-11-16. Version 0.7.0 adds Composer and Maven imports and JSON output for more CLI commands. It changes rules output and usage-error reporting.

Physical iPhone Safari, screen-reader control announcements and native EndNote import still need verification.

Dataset metadata and required-field checks are implemented, and the consuming repositories have adopted them. The playground includes form mode and field lookup. Documentation is searchable, and installation, playground and reference guides stay on this website. See the [release notes](../CHANGELOG.md) for the changes.

## Next

- Use a CiteSync release to compare the built wheel and source distribution with its citation files. Publish the commands and show what each format carries or omits. [Release metadata decision](decisions/0007-check-release-metadata.md)
- Let maintainers opt in to filling specific missing fields in existing citation files, with additions visible in `write --diff`. [Release metadata decision](decisions/0007-check-release-metadata.md)
- Test whether Software Heritage indexes a CodeMeta 4.0 record and preserves the fields used in the pilot. [CodeMeta version decision](decisions/0006-field-conversions-from-codemeta-drift-and-codemeta-3.md)
- Submit CiteSync to the Research Software Directory.

## Adoption

Use the worked release example in one outside project. Use its feedback to propose the check for a research software template. The longer-term goal is for a template to ship the check and for ten outside repositories to run it.

## Design boundaries

- Keep CRediT roles intact in CodeMeta. Supply Zenodo contributor types explicitly. [Contribution role decision](decisions/0005-vocabulary-blind-roles.md)
- Add new field locations to codemeta-drift and adopt them in CiteSync through a reviewed mapping update. [Mapping decision](decisions/0002-vendored-mapping.md)
- Read package metadata as data. For projects that compute metadata at build time, use the output of the existing build. [Python distribution metadata](formats.md#python-distribution-metadata)

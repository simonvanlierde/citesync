# Documentation

citesync keeps software citation files in step with the metadata in your repository. Use the command line for repeatable checks, or generate files in the [browser playground](https://simonvanlierde.com/citesync/) without installing Python.

## Start here

- [Install citesync](getting-started.md), then run `citesync check` in your repository.
- [Create a CITATION.cff](init.md) from package metadata when you do not have one yet.
- [Use the playground](../playground/README.md) to paste a file or enter project details, review the results and download citation files.

## Work with a repository

- [Check that files agree](check.md) and understand findings and exit codes.
- [Update citation files](write.md) while preserving comments and unmapped metadata.
- [Require selected fields](config.md#require-values-in-selected-files), such as authors, licences or a release DOI.
- [Keep software and dataset metadata separate](datasets.md), including their licences.
- [Set up a pre-commit hook](../README.md#pre-commit-hook) to catch metadata drift before committing.
- [Export citations](export.md) for publications, websites and reference managers.
- [Cite software with Pandoc or Quarto](pandoc.md).

## Reference

- [Configuration](config.md): source files, required values and other settings.
- [Supported files](formats.md): which formats citesync reads, checks and writes.
- [Rules](rules.md): findings and how to address them.
- [Output formats](output.md): JSON, GitHub annotations and SARIF.
- [Contribution records](contributions.md): carrying people and roles between tools.

## About the project

- [Release notes](../CHANGELOG.md).
- [Roadmap](roadmap.md).
- [Tests on real repositories](tested-repositories.md).
- [Design decisions](decisions/index.md).
- [Contributing](../.github/CONTRIBUTING.md).

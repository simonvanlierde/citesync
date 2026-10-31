# Supported files

Reading, updating and creating a file are separate operations:

| File | Read and compare | Update an existing file | Create a new file |
| --- | --- | --- | --- |
| CITATION.cff | Yes | Supported fields | `citesync init` |
| codemeta.json | Yes | Supported fields | `citesync write`, when listed in `files` |
| .zenodo.json | Yes | Supported fields | `citesync write`, when listed in `files` |
| pyproject.toml | Yes, `[project]` metadata | Selected fields, opt-in | No |
| Cargo.toml | Yes, package metadata | Selected fields, opt-in | No |
| package.json | Yes, npm package metadata | Selected fields, opt-in | No |

Any supported file can be the source. For example, `citesync init` can read a package manifest
to create CITATION.cff. It does not require an existing codemeta.json.

The [init guide](init.md) explains how fields are combined and names are split.
The [write guide](write.md) describes file creation, omitted fields and preservation of existing data.
The [configuration reference](config.md) lists the manifest fields that can be updated.

Package manifests also control builds, dependencies and publishing. citesync handles their
citation metadata; it does not generate complete package configurations.

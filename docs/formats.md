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
| PKG-INFO / METADATA | Yes, Python Core Metadata | Never | No |

Any supported file can be the source. For example, `citesync init` can read a package manifest
to create CITATION.cff. It does not require an existing codemeta.json.

The [init guide](init.md) explains how fields are combined and names are split.
The [write guide](write.md) describes file creation, omitted fields and preservation of existing data.
The [configuration reference](config.md) lists the manifest fields that can be updated.

Package manifests also control builds, dependencies and publishing. citesync handles their
citation metadata; it does not generate complete package configurations.

## Python distribution metadata

Use an extracted sdist PKG-INFO or wheel METADATA as an explicit source. No package build, import, archive extraction or setup.py execution runs:

```sh
citesync init --source lensgrind.egg-info/PKG-INFO
citesync write --source lensgrind.egg-info/PKG-INFO
```

List codemeta.json and .zenodo.json in `files` when creating them. Distribution metadata is not discovered automatically or accepted as a writable manifest; its bytes stay unchanged. The browser accepts either filename, detects pasted headers as METADATA and generates the same citation outputs.

The reader follows the [Python Core Metadata specification](https://packaging.python.org/en/latest/specifications/core-metadata/), using email-header parsing and UTF-8. It supports versions 1.0, 1.1, 1.2 and 2.1 through 2.6, with a 1 MB input limit. Name and Version are required. Malformed headers, conflicting single-value fields, repeated Project-URL labels with different URLs, unsupported metadata versions and invalid License-Expression values are errors.

Name, Version, Summary (or Description/body), author names, keywords, licence and repository URLs feed the existing PEP 621 codecs and curated field mapping. No second crosswalk is maintained. Repeated Author, Author-email and Project-URL headers are read in full. Named email contacts enrich matching author names; other named contacts are appended. Unnamed email addresses do not invent author names. Commas separate names in Author; quote a name containing a comma and review inferred name splits. Email addresses and unrelated URL labels are not citation fields. Maintainers never become authors automatically.

License-Expression is checked as SPDX. A legacy License value is carried over only when it is itself a valid SPDX expression; other free text is omitted with a `metadata-omitted` notice. Private LicenseRef values also get a notice rather than an invented public SPDX URL. Missing optional fields stay absent. No DOI or ORCID is inferred from package URLs or email addresses.

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
| DESCRIPTION | Yes, static R package metadata | Never | No |
| Project.toml / JuliaProject.toml | Yes, Julia metadata | Never | No |
| PKG-INFO / METADATA | Yes, Python Core Metadata | Never | No |
| Exports: `.bib`, `.csl.json`, `.apa.txt`, `.jsonld` | Compared whole with what the source gives | Made again whole | `citesync write`, when listed in `exports` ([exports](export.md)) |

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

## R and Julia imports

Use these files as an explicit source; they are not discovered automatically or accepted as writable manifests:

```sh
citesync init --source DESCRIPTION
citesync init --source Project.toml
```

List codemeta.json and .zenodo.json in `files` when creating those files with `write`. Uploaded files also work in the playground, with matching examples and automatic detection. Inputs stay byte-identical; no R, Julia, build script or package import runs. The adapters normalize into the existing CodeMeta field shapes before using the curated mapping, so no new mapping release is needed.

R DESCRIPTION uses the package's `Title` as the citation name, falling back to `Package` if no title is supplied. It reads Description, Version, ISO Date, licence and a repository URL when one can be identified. A homepage is not assumed to be a repository. UTF-8 and ASCII are supported; convert other encodings before importing.

`Authors@R` supports literal `person()` calls, optionally joined by `c()`. Given and family names can be strings or `c()` vectors of strings. The first two positional arguments are given and family names; use named email, role and comment arguments. Named `comment = c(ORCID = "...")` preserves an ORCID. `aut` people are authors; people with `ctb` and no `aut` are contributors. `cre` alone never makes a maintainer an author. Other roles are not translated into CRediT or Zenodo types. Calls such as `paste()`, `readRDS()` and `system()`, variables and other expressions are rejected rather than evaluated. Free-text Author and Maintainer fields are not parsed; use Authors@R or enter structured details in the playground.

R's common GPL/LGPL/AGPL version forms and BSD abbreviations are normalized to SPDX. Licence alternatives use `OR`. Ambiguous licences, LicenseRef values and `+ file LICENSE` terms are omitted with a notice: the importer does not read or guess external licence terms. Non-ISO dates are also omitted with a notice. Package names are never treated as DOIs.

Julia supports string authors and CFF-shaped person/entity tables, including name particles and ORCIDs. Name, version, description and SPDX licence metadata are imported when supplied; the importer is not a full Julia package validator. A project used only as an environment can omit name, version and authors; those values are not invented. Its partial metadata can be transferred to the playground's details form. UUIDs identify Julia packages, not DOIs, and are not put in the DOI field. JuliaProject.toml is an alias of Project.toml.

Specifications: [Writing R Extensions](https://cran.r-project.org/doc/manuals/r-release/R-exts.html#The-DESCRIPTION-file), [Julia project files](https://pkgdocs.julialang.org/v1/toml-files/). The original R crosswalk's Title, Author-role and Description mappings also informed the normalization; the typed author tables follow Julia's current CFF-based specification.

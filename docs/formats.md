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
| typst.toml | Yes, Typst package metadata (`[package]`) | Selected fields, opt-in | No |
| _extension.yml / _extension.yaml | Yes, a Quarto extension's `title`, `version` and `author` | Selected fields, opt-in | No |
| DESCRIPTION | Yes, static R package metadata | Never | No |
| Project.toml / JuliaProject.toml | Yes, Julia metadata | Never | No |
| PKG-INFO / METADATA | Yes, Python Core Metadata | Never | No |
| ro-crate-metadata.json | Yes, an RO-Crate 1.3 root dataset | Never | No, [sourceledger](https://github.com/simonvanlierde/sourceledger) `release` makes it |
| croissant.json | Yes, a Croissant 1.1 dataset | Never | No, sourceledger `release` makes it |
| Exports: `.bib`, `.csl.json`, `.apa.txt`, `.jsonld`, `.datacite.xml`, `.ris`, `.enw` | Compared whole with what the source gives | Made again whole | `citesync write`, when listed in `exports` ([exports](export.md)) |

Any supported file can be the source. For example, `citesync init` can read a package manifest
to create CITATION.cff. It does not require an existing codemeta.json.

The [init guide](init.md) explains how fields are combined and names are split.
The [write guide](write.md) describes file creation, omitted fields and preservation of existing data.
The [configuration reference](config.md) lists the manifest fields that can be updated.

## Dataset files

sourceledger's `release` copies the name, description, licence, version, DOI, release date and authors from codemeta.json into `ro-crate-metadata.json` and `croissant.json`. `check` compares them with the source like a citation file, on every field they hold, so a release made from a stale codemeta.json shows up. It finds them at the repo root; a release folder goes under `manifests`, such as `manifests = ["pyproject.toml", "release/ro-crate-metadata.json"]`. `write` never changes them: fix the source, run `citesync write`, then `sourceledger release` again.

An RO-Crate is read from its root data entity, the `@graph` entry with `@id` `./`. Each reference there, such as an author written as `{"@id": "https://orcid.org/..."}`, is read through the entity with that `@id`. A crate without that entry, such as a detached crate whose root is a URL, is [`unreadable`](rules.md#unreadable). Both files are read through codemeta-drift's `ro-crate` and `croissant` rows ([decision 0002](decisions/0002-vendored-mapping.md)).

## Plugin manifests

A Typst package's `typst.toml` and a Quarto extension's `_extension.yml` carry a version and authors that should move with each release. citesync reads them through their own rows in the field mapping: `typst.toml` gives `name`, `version`, `authors`, `license`, `description`, `repository` and `keywords`; `_extension.yml` gives `title` (as the name), `version` and its one `author` (an `author` list makes the file `unreadable`). A field a format has no row path for, such as a Quarto extension's licence or keywords, is neither read nor written. A Quarto extension lives under `_extensions/<name>/`, so list it under `manifests`:

```toml
manifests = ["typst/typst.toml", "quarto/_extensions/lensgrind/_extension.yml"]
write-manifests = ["version"]
```

A `typst.toml` or `_extension.yml` at the repo root is read by default, as the other manifests are. `write` edits `_extension.yml` through the same YAML round trip as CITATION.cff, so its comments and quoting stay.

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

The reader turns the headers into header names and values, and codemeta-drift's pkg-info rows read Name, Version, Summary, author names, keywords, licence and the repository URL from them ([coverage matrix](https://github.com/simonvanlierde/codemeta-drift/blob/main/docs/coverage.md)). Description and the message body hold the README, so they aren't read as the summary. The repository is the first Project-URL labelled source, repository, sourcecode or github, in that order, with labels compared in lower case without punctuation or spaces, so `Source Code` matches; with none of those, it's Home-page. Repeated Author, Author-email and Project-URL headers are read in full. Named email contacts enrich matching author names; other named contacts are appended. Unnamed email addresses do not invent author names. Commas separate names in Author, as the pyproject.toml spec writes them, except that a company suffix (Inc, LLC, Ltd, GmbH, PBC, Corp) stays with the name before it and "et al." is dropped. Quote a name containing a comma, such as "Sun, Junyi", and review inferred name splits. Email addresses and unrelated URL labels are not citation fields. Maintainers never become authors automatically.

License-Expression is checked as SPDX. A legacy License value is carried over only when it is itself a valid SPDX expression; other free text is omitted with a `metadata-omitted` notice. Private LicenseRef values also get a notice rather than an invented public SPDX URL. Missing optional fields stay absent. No DOI or ORCID is inferred from package URLs or email addresses.

## R and Julia imports

Use these files as an explicit source; they are not discovered automatically or accepted as writable manifests:

```sh
citesync init --source DESCRIPTION
citesync init --source Project.toml
```

List codemeta.json and .zenodo.json in `files` when creating those files with `write`. Uploaded files also work in the playground, with matching examples and automatic detection. Inputs stay byte-identical; no R, Julia, build script or package import runs. The reader parses each file into its own fields, with `Authors@R` as a list of people, and codemeta-drift's r-description and julia rows say which fields hold each value.

R DESCRIPTION gives the citation name as `Package: Title`, such as `lensgrind: Measure Microscope Optics`, the way cffr and codemetar write it, or `Package` alone when there's no title. It reads Description, Version, ISO Date, licence and a repository URL when one can be identified. A homepage is not assumed to be a repository. UTF-8 and ASCII are supported; convert other encodings before importing.

`Authors@R` supports literal `person()` calls, optionally joined by `c()`. Given and family names can be strings or `c()` vectors of strings. The first two positional arguments are given and family names; use named email, role and comment arguments. Named `comment = c(ORCID = "...")` preserves an ORCID. `aut` people are authors; people with `ctb` and no `aut` are contributors, so a person with both roles is one author. `cre` alone never makes a maintainer an author. Other roles are not translated into CRediT or Zenodo types. Calls such as `paste()`, `readRDS()` and `system()`, variables and other expressions are rejected rather than evaluated. Free-text Author and Maintainer fields are not parsed; use Authors@R or enter structured details in the playground.

R's common GPL/LGPL/AGPL version forms and BSD abbreviations are normalized to SPDX. Licence alternatives use `OR`. Ambiguous licences, LicenseRef values and `+ file LICENSE` terms are omitted with a notice: the importer does not read or guess external licence terms. Non-ISO dates are also omitted with a notice. Package names are never treated as DOIs.

Julia supports string authors and CFF-shaped person/entity tables, including name particles and ORCIDs. Name and version are imported when supplied. Project.toml has no description or licence field, so a `description` or `license` key someone adds isn't read; the importer is not a full Julia package validator. A project used only as an environment can omit name, version and authors; those values are not invented. Its partial metadata can be transferred to the playground's details form. UUIDs identify Julia packages, not DOIs, and are not put in the DOI field. JuliaProject.toml is an alias of Project.toml.

Specifications: [Writing R Extensions](https://cran.r-project.org/doc/manuals/r-release/R-exts.html#The-DESCRIPTION-file), [Julia project files](https://pkgdocs.julialang.org/v1/toml-files/). The original R crosswalk's Author-role and Description mappings also informed the normalization; the typed author tables follow Julia's current CFF-based specification.

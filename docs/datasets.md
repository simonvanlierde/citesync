# Keep software and dataset metadata separate

A repository can contain software and data with different licences. Keep software metadata in `codemeta.json` and dataset metadata in a separate file. citesync can keep their shared release details in step without replacing the software licence.

## Configure dataset CodeMeta

Start with a `CITATION.cff` that describes the software. Review the dataset's rights before choosing a licence: a software licence does not grant permission to redistribute the data.

Add these settings to `citesync.toml`, or the existing [configuration](config.md):

```toml
dataset-codemeta = "dataset.codemeta.json"
dataset-license = "CC-BY-4.0"
```

`CC-BY-4.0` is an example. Replace it with the dataset's actual licence, expressed as an SPDX identifier, expression or licence URL. Do not choose a licence when its terms are unknown.

Preview the changes:

```sh
citesync write --diff
```

The preview exits 1 when it would change files. Review its output, then write and check the files:

```sh
citesync write && citesync check
```

citesync creates the dataset file with `@type: Dataset`. It takes shared fields from the software source and uses `dataset-license` for the dataset licence. Other citation files keep the software licence. The dataset path must be distinct from every software input and export.

When only `dataset-license` is set, the dataset path defaults to `dataset.codemeta.json`. An existing file with that name is discovered automatically. When `dataset-license` is absent, the dataset uses the source licence; use an explicit setting whenever the rights differ.

This file derives shared release details from the source. If the dataset has its own title, authors, version or release date, maintain its metadata independently instead of overwriting it from the software record.

## Require release details

Add requirements for values that your release needs:

```toml
required-fields = { "dataset.codemeta.json" = ["name", "author", "license", "version"] }
```

Use the configured dataset path if it differs from this example. Run `citesync check` again. A missing or empty normalized value reports `required-field-missing` and exits 1, even when the software source also lacks it.

Requirements check completeness, not the truth of the metadata. They do not invent missing authors, licences, identifiers or dates. See [required fields](config.md#require-values-in-selected-files) for supported terms and limits.

## Use the file with sourceledger

For an existing [sourceledger](https://github.com/simonvanlierde/sourceledger) project configured to produce RO-Crate or Croissant metadata, pass the dataset file explicitly:

```sh
sourceledger release release/ --codemeta dataset.codemeta.json
```

Choose a new output directory for each release. To check the generated metadata with citesync, include the existing files under `manifests`:

```toml
manifests = ["release/ro-crate-metadata.json", "release/croissant.json"]
```

That list replaces the default manifest discovery. Include any package manifests you also want checked, and list only release files that sourceledger generated. Then run:

```sh
citesync check
```

citesync compares these files with the source and the configured dataset licence. It never rewrites RO-Crate or Croissant files. When they are stale, update the source, run `citesync write`, then generate a new sourceledger release. See [dataset file support](formats.md#dataset-files) for parsing limits.

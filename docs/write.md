# How `citesync write` works

`citesync write` fixes what `check` reports, and nothing more. `citesync write --diff` prints the same edits as a unified diff and writes nothing, and on stderr how many findings it would fix in how many files. It exits 1 when there is a change or a file it can't read, so CI can run it.

## What it writes

It writes every citation file that isn't the source. It changes a manifest only for the fields listed in `write-manifests` (see [config.md](config.md)).

PKG-INFO, METADATA, R DESCRIPTION and Julia Project.toml/JuliaProject.toml are read-only sources, even when `write-manifests` is enabled.

It leaves these alone:

- a field a file leaves out: a .zenodo.json without a version never gains one;
- a field the source doesn't hold (no DOI in pyproject.toml);
- values that compare equal, such as `v1.2.3` against `1.2.3`;
- findings whose rule is in `ignore`, and `unreadable` files.

## Create citation files

List a missing codemeta.json or .zenodo.json under `files` to create it from the source:

```toml
# citesync.toml
files = ["codemeta.json", ".zenodo.json"]
```

Preview the files with `citesync write --diff`. Run `citesync write` to create them.
Without that setting, write only updates files that exist. Ignoring `file-missing` also prevents creation.
[`citesync init`](init.md) creates a CITATION.cff. Files under `exports` (BibTeX, CSL-JSON, APA, JSON-LD) are created when missing and made again whole whenever they differ from the source ([citation exports](export.md)).

A new codemeta.json gets the configured `codemeta-version`, else 3.0, the version Software Heritage reads.
A new .zenodo.json gets `upload_type: software` and the supported fields the source holds.
Repository URLs and Software Heritage identifiers become separate `related_identifiers` entries.
Creators use Zenodo's `Family, Given` spelling and bare ORCID iDs.

Review the new .zenodo.json before publishing a release. Only the compared fields are copied;
funding, affiliations, communities and references need separate review. Missing source fields stay absent.
The output is metadata for Zenodo's GitHub integration, not a complete deposition API request.
Write reports fields it cannot represent, including compound licences, authors without names and
contributors without a type when `zenodo-contributor-type` is not configured. It leaves those fields out rather than choosing values.
A successful `citesync check` confirms agreement, not that Zenodo will accept a release.

## How it spells values

Write keeps each file's layout: comments, key order, quoting and indentation. It spells each value the way that file does, such as Zenodo's `"Family, Given"` and lowercase licence ids, or semver in Cargo.toml and package.json.

Some values a file can't hold, such as a licence with `AND` in CITATION.cff, or a post-release version in Cargo.toml. Write leaves those as they were, and the finding says why.

## Authors and contributors

Contributors are written as authors are. The [contribution guide](contributions.md)
shows the checked people/role contract and each format's limits.

- An author whose name or ORCID matches keeps the rest of their entry, such as an email or affiliation. Anyone else gets a new entry.
- If that would drop an old entry with more than a name and ORCID, for example after a rename, write leaves that file's authors for you to edit.
- The same goes for an old entry with an ORCID when a new author without one comes in: that may be the same person renamed, and write won't guess.
- An author with only a name, such as an organization, keeps it as a family name. A new one goes into codemeta.json as an `Organization`.
- Zenodo requires a contributor `type`. Set `zenodo-contributor-type = "Researcher"` (or another [supported type](config.md)) to seed new contributors, including in a newly created .zenodo.json. Existing types are preserved; CRediT roles never determine the type. In an existing target, an explicit empty `contributors: []` allows additions; an absent field stays absent. Without a configured type, add new contributors by hand.
- A Cargo field inherited with `.workspace = true` stays as it is, and the finding says so. Change it in `[workspace.package]`.

## Output and exit codes

Write prints `wrote <file>` for each file it changed, to stderr with `--format json`, `github` or `sarif`. `--quiet` drops it. Then it reports the findings that are left, as `check` does, each with what to do about it, and ends with a count such as `9 fixed, 6 left in 6 files`. The exit codes are those of [`check`](check.md#findings-and-exit-codes).

## Safety

Write puts every file in a temporary file beside it before it moves any into place, so a failure leaves your files as they were. Only a failed move can leave some files written and others not. It writes through a symlink that points inside the repo. It doesn't touch a file that wouldn't change, and CRLF line ends stay CRLF, and so does a CITATION.cff's byte order mark. A file with both LF and CRLF line ends gets the more common one, or LF on a tie.

In CITATION.cff, write may change a few things around what it edits. A list item it replaces loses its end-of-line comment. A sequence indented differently from the first one is reindented to match it. A closing `...` line is dropped.

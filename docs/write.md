# How `citesync write` works

`citesync write` fixes what `check` reports, and nothing more. `citesync write --diff` prints the same edits as a unified diff and writes nothing; it exits 1 when there is a change, or a file it can't read (listed on stderr), so CI can run it.

## What it writes

It writes every citation file that isn't the source, and a manifest only for the fields listed in `write-manifests` (or all of them with `"all"`, see [config.md](config.md)). A field a file leaves out stays out: a .zenodo.json without a version never gains one. When the source has no value for a field (no DOI in pyproject.toml), write leaves that field alone in the other files. It can't yet create a citation file listed under `files` that doesn't exist.

Values that compare equal stay as written: write leaves `v1.2.3` against `1.2.3`, and `LCA` against `lca` unless `keywords-case-sensitive` is set. A finding whose rule `ignore` lists is not written, and an `unreadable` file is never written.

## How it spells values

It keeps each file's layout: comments, key order and quoting in CITATION.cff, comments in TOML, and in JSON the key order, indentation, one-line arrays and final newline. Each value is spelled the way that file spells it: Zenodo's `"Family, Given"` and lowercase licence ids, a DOI URL in codemeta.json, where a schema.org PropertyValue keeps its other keys, semver in Cargo.toml and package.json, PEP 440 in pyproject.toml.

A value the file can't spell is left as it was, and its finding says why:

- a compound licence in .zenodo.json;
- a licence with `AND` or `WITH` in CITATION.cff or codemeta.json (`OR` becomes a list);
- in Cargo.toml and package.json, a version semver has no spelling for (a post-release such as `1.2.3.post1`, an epoch, more than three numbers);
- in pyproject.toml, a version that isn't PEP 440.

## Authors

An author with only a name, such as an organization (`name` in CITATION.cff and codemeta.json), counts as a family name and keeps it; a new one is written to codemeta.json as an `Organization`, not a `Person`. An author whose name or ORCID matches keeps the rest of their entry, such as an email or affiliation; anyone else gets a new entry. When that would drop an old entry holding more than a name and ORCID, such as after a renaming in a manifest, write leaves that file's authors for you to edit. A Cargo field inherited with `.workspace = true` is left as it is: change it in the workspace's `[workspace.package]`.

## Output and exit codes

It prints `wrote <file>` for each file it changed (to stderr with `--format json` or `github`, and not at all with `--quiet`), then reports the findings left as `check` does, in the same [formats](output.md), each with what to do: edit it by hand (with the reason, when write could have written it but didn't), or add the field to `write-manifests`. Exit 0 when no error finding remains, 1 when one does (an unreadable file included), and 2 when citesync couldn't run.

## Safety

Every file is written to a temporary file beside it before any is moved into place, so a failure leaves the files as they were, unless a move itself fails, which leaves the files moved before it written. A symlinked file is written through the link, CRLF line ends stay CRLF (a file that mixes LF and CRLF comes back all CRLF), and a file that would not change is not touched.

Known limits of the CITATION.cff round trip: an end-of-line comment aligned with spaces after a value (`title:    x   # c`) is reflowed, a second sequence indented differently from the first is reindented to match it, and a closing `...` and a byte-order mark are dropped.

# How `citesync init` works

`citesync init` writes a CITATION.cff for a repo that has none. It reads the files the repo already has: codemeta.json, .zenodo.json and the package manifests (pyproject.toml, Cargo.toml, package.json). `citesync init --diff` prints the new file as a diff and writes nothing. It exits 0 whenever it can run, though `write --diff` exits 1 when it shows a change.

## Where each field comes from

Each field but the keywords comes from the first file that holds it, in this order: the file named by `--source` or the `source` setting, then codemeta.json, .zenodo.json, pyproject.toml, Cargo.toml and package.json. So an author's ORCID and the split into given and family names come from a citation file when there is one. From a manifest's one-string name, the last word becomes the family name. The keywords come from every file, each once, so each manifest's keywords are in CITATION.cff as check requires.

The new file holds `cff-version: 1.2.0`, the standard `message`, `type: software`, and each of these the files give: title, abstract (from the description), version, release date, authors, DOI, repository URL, licence and keywords. It passes `citesync check` against the files it came from.

A value CITATION.cff can't hold, such as a licence with `AND`, is left out, and `init` says why after `wrote CITATION.cff`. So is a licence list, such as Cargo's `MIT OR Apache-2.0`, when there is no .zenodo.json: Zenodo would refuse it ([`zenodo-license-list`](rules.md#zenodo-license-list)).

## When it refuses

`init` exits 2 and writes nothing when:

- CITATION.cff exists already. To make it agree with another file, use [`citesync write`](write.md) with `--source`.
- there is no codemeta.json, .zenodo.json or manifest, or one can't be read;
- no file gives a title or any author, which CITATION.cff requires.

It never asks a question and never reads the network, so GitHub topics don't become keywords.

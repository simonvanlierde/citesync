# Cite a DOI, arXiv ID or GitHub repository

Use `citesync cite` to read public metadata and print a citation. DOI lookups use
Crossref and DataCite. Use the DOI for the exact edition or release you want to
cite. A concept DOI and a version DOI identify different records.

```sh
citesync cite 10.7717/peerj.4375 --format csl-json
citesync cite arxiv:2205.01833v1 --format ris
citesync cite https://github.com/simonvanlierde/citesync --format bibtex
```

BibTeX is the default. BibTeX, CSL-JSON and RIS support papers, preprints,
software and datasets. CFF and CodeMeta support software and datasets.
CFF requires a titled record with at least one named author.

An arXiv ID with a version suffix selects that version. A journal DOI supplied
by arXiv appears as a related identifier in JSON. To cite the journal record,
resolve its DOI separately.

GitHub lookups record the default branch's commit and read its root
`CITATION.cff` or `codemeta.json` at that commit. Add `--preferred` to cite a
supported `preferred-citation` in CFF. The preferred citation has its own title,
people and identifiers. For the exact software release, use its version DOI.

## Inspect authors and references

```sh
citesync cite 10.7717/peerj.4375 --json --openalex W2741809807
```

The JSON report includes the normalized work, selected citation, any preferred
citation, and provenance. It lists the mapping pin and each provider request's
URL, retrieval time and response hash. Crossref's deposited CRediT roles appear
as work-scoped evidence. OpenAlex evidence is optional. The command
checks the supplied work's DOI or arXiv identity against the selected citation.

Compare author identities and observed role IDs with a CRediT Matrix roster
before applying assignments. OpenAlex roles describe the cited work. An author
with the same name on another work needs a separate identity check. The
reference list keeps the printed text, the source DOI and the OpenAlex match
in separate fields. Unmatched lines stay in the list for review. A curator can
pass the DOI or a reviewed OpenAlex work ID through the same command. An
OpenAlex work ID resolves through the work's DOI or arXiv identifier.

## Replay a citation offline

Use a new directory to capture the provider's response bytes. Check the
provider's reuse terms before sharing a capture.

```sh
citesync cite 10.7717/peerj.4375 --save-responses citation-capture
citesync cite 10.7717/peerj.4375 --replay citation-capture
```

Replay checks each response's SHA-256 and the mapping hash listed in
`citation-capture/responses.json`. Use the same CiteSync mapping and provide the
same identifier and lookup options. Change `--format` to render another citation
from those inputs.

To retain the inputs in a dataset provenance log, create a Sourceledger file
source for each response you want to retain. Use the URL and SHA-256 recorded
in the manifest. Then run `sourceledger record` with the captured file and
retrieval time. Keep the manifest beside the archived inputs. Restore the
same filenames under the capture directory before replay. See
[record a file another tool downloaded](https://simonvanlierde.com/sourceledger/docs/recipes/#record-a-file-another-tool-downloaded).

## Exit codes

- `0` prints a citation.
- `2` reports invalid arguments or an unsupported identifier.
- `3` reports a missing record, unavailable provider, unsupported output
  for the work's type, or invalid capture.
- `130` means Ctrl-C interrupted the command.

The CLI makes its request only for `cite`. The local `check`, `write` and
`export` commands work offline.

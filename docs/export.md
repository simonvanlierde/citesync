# Citation exports

`citesync export --format apa|bibtex|csl-json|jsonld` prints a citation made from the source file. To keep committed copies up to date, list them under `exports` in the [config](config.md):

```toml
exports = ["CITATION.bib", "citation.csl.json", "citation.apa.txt", "schema.jsonld"]
```

`citesync write` then creates and updates each file. `citesync check` reports one that is missing or out of date as [`export-stale`](rules.md#export-stale), so the hook catches a release that changed the version but not the exports. Each export is generated whole, so don't edit it by hand.

The suffix picks the format:

| Suffix | Format | Notes |
| --- | --- | --- |
| `.bib` | biblatex-software `@software` | Field names come from codemeta-drift's bibtex rows. Names in braces, so particles and organisations stay whole. `url` and `year` are written next to `repository` and `date`, so plain BibTeX styles, which print `@software` as `@misc`, still show them. |
| `.csl.json` | CSL-JSON, type `software` | For Pandoc, Zotero and other CSL processors ([Pandoc guide](pandoc.md)). |
| `.apa.txt` | APA 7 software reference, one line | Initials from given names (`J.-B.` for Jean-Baptiste). Up to 20 authors, then the first 19, an ellipsis and the last. `(n.d.)` with no release date. Links the DOI, else the repository. |
| `.jsonld` | schema.org `SoftwareSourceCode` | The plain `https://schema.org` context, which search engines read, so a website can embed it in a `<script type="application/ld+json">` tag. CodeMeta's context isn't read by them. |

The citation key in BibTeX and CSL-JSON is the title up to any subtitle, in lowercase ASCII with dashes: `CRediT Matrix: drafting CRediT contribution statements` gives `credit-matrix`.

## Citation files

`citesync export --format cff|codemeta|zenodo` prints the CITATION.cff, codemeta.json or .zenodo.json citesync would make from the source, and writes nothing. Each is built as [`init`](init.md) builds CITATION.cff and as [`write`](write.md#create-citation-files) creates the other two: each field comes from the first file that holds it, and the keywords from every file, so the printed file passes `check`. The CITATION.cff needs no CITATION.cff to read, just as `init` doesn't, and like `init` it stops when any of those files can't be read, or when a source named with `--source` or `source` is missing. What the file can't hold goes to stderr as `leaving out <field>: <why>`, so `citesync export --format cff > CITATION.cff` stays a clean file.

These three can't go under `exports`: list them under `files`, and `write` updates them field by field, keeping comments, key order and fields citesync doesn't map. An export is made again whole, which would drop those.

## Where the values come from

The values come from the source. A field the source doesn't hold, such as the DOI when pyproject.toml is the source, comes from the first other file that holds it, in the order [check](check.md) reads them. The BibTeX `url` and CSL `URL` are the repository URL. A release date that isn't a full `YYYY-MM-DD` date is left out of BibTeX, CSL-JSON and APA, and the command says so on stderr. JSON-LD keeps the date as written.

Use the files at build time: a static site imports `schema.jsonld` or `citation.apa.txt` without running Python, and the [playground](../playground/README.md) offers the same four files.

# Citation exports

`citesync export --format apa|bibtex|csl-json|jsonld` prints a citation made from the source file. To keep committed copies up to date, list them under `exports` in the [config](config.md):

```toml
exports = ["CITATION.bib", "citation.csl.json", "citation.apa.txt", "schema.jsonld"]
```

`citesync write` then creates and updates each file. `citesync check` reports one that is missing or out of date as [`export-stale`](rules.md#export-stale), so the hook catches a release that changed the version but not the exports. Each export is generated whole, so don't edit it by hand.

The suffix picks the format:

| Suffix | Format | Notes |
| --- | --- | --- |
| `.bib` | BibTeX `@misc` | Names in braces, so particles and organisations stay whole. Version in `note`. |
| `.csl.json` | CSL-JSON, type `software` | For Pandoc, Zotero and other CSL processors ([Pandoc guide](pandoc.md)). |
| `.apa.txt` | APA 7 software reference, one line | Initials from given names (`J.-B.` for Jean-Baptiste). Up to 20 authors, then the first 19, an ellipsis and the last. `(n.d.)` with no release date. Links the DOI, else the repository. |
| `.jsonld` | schema.org `SoftwareSourceCode` | The plain `https://schema.org` context, which search engines read, so a website can embed it in a `<script type="application/ld+json">` tag. CodeMeta's context isn't read by them. |

The citation key in BibTeX and CSL-JSON is the title up to any subtitle, in lowercase ASCII with dashes: `CRediT Matrix: drafting CRediT contribution statements` gives `credit-matrix`.

## Where the values come from

The values come from the source. A field the source doesn't hold, such as the DOI when pyproject.toml is the source, comes from the first other file that holds it, in the order [check](check.md) reads them. The BibTeX `url` and CSL `URL` are the repository URL. A release date that isn't a full `YYYY-MM-DD` date is left out of BibTeX, CSL-JSON and APA, and the command says so on stderr. JSON-LD keeps the date as written.

Use the files at build time: a static site imports `schema.jsonld` or `citation.apa.txt` without running Python, and the [playground](../playground/README.md) offers the same four files.

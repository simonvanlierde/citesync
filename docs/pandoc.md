# Cite software with Pandoc or Quarto

Download `citation.csl.json` or `citation.bib` from the playground. Pandoc already accepts CSL-JSON and BibTeX as bibliography files; no citesync filter is needed. The exports use the citation key `software`; give each entry a distinct key when combining several exports.

For a Markdown document:

```markdown
We used lensgrind for the optical measurements [@software].
```

Render it with Pandoc:

```sh
pandoc paper.md --citeproc --bibliography citation.csl.json -o paper.html
```

Or add the bibliography to a Quarto document’s front matter:

```yaml
bibliography: citation.csl.json
```

Review author names and any omitted fields before using an export. A date appears only when the source supplies one. The current CLI checks and synchronizes metadata; bibliography downloads are available in the playground.

Credit Matrix’s Quarto/Pandoc filter renders manuscript CRediT contribution statements. That is separate from citing a software release. Keep software authors, version and DOI separate from manuscript authors, roles and DOI. Software contribution Roles can remain in CodeMeta; they are not silently converted to Zenodo contributor types or manuscript authorship.

See [Pandoc’s bibliography documentation](https://pandoc.org/MANUAL.html#specifying-bibliographic-data) for supported formats. Dedicated Quarto/front-matter export is not needed for this bibliography workflow.

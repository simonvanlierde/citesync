# Output formats

`citesync check` and `citesync write` print text by default. The text format is in [check.md](check.md#findings-and-exit-codes).

## JSON

`--format json` prints one document:

```json
{
  "version": 1,
  "tool": { "name": "citesync", "version": "0.1.0" },
  "summary": { "files": 3, "errors": 1, "warnings": 0, "info": 0 },
  "findings": [
    {
      "rule": "version-mismatch",
      "severity": "error",
      "file": "codemeta.json",
      "term": "version",
      "message": "'2.0.0', CITATION.cff has '1.0.0'",
      "help": "Make the file agree with the source, or the other way round if the source is wrong.",
      "url": "https://github.com/simonvanlierde/citesync/blob/main/docs/rules.md#version-mismatch",
      "line": null,
      "column": null
    }
  ]
}
```

Findings are sorted by file, rule and field, and positions count from 1. A value longer than 80 characters is cut to 77 and ends in `...` in the message. `file` is null for a field no file holds, and `term` (the CodeMeta term) is null for `unreadable`. JSON always lists every finding: `-q` and `-v` change only the text and GitHub output.

[tests/output.schema.json](../tests/output.schema.json) is the JSON Schema. A minor release may add rule ids and optional fields; ignore what you don't know. Removing or retyping a field bumps `version`, in a major release.

## GitHub

`--format github` writes one workflow annotation per finding, titled `citesync <rule>`, and ends with a notice that counts them all, since GitHub shows only the first ten of each level.

## SARIF

`--format sarif` writes one SARIF 2.1.0 log: a `citesync` driver with its version and a `rules` entry (with `helpUri`) for each rule that appears, and a result per finding with `ruleId`, `level` (`error`, `warning`, or `note` for info), the text format's message, and the repo-relative file as `uri`, plus a `region` when the finding has a position. A finding on no file has no location. Like the text format, it leaves out info findings unless you pass `-v`. Exit codes are the same as for the other formats.

GitHub code scanning takes it through `github/codeql-action/upload-sarif`:

```yaml
- run: uvx citesync check --format sarif > citesync.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: citesync.sarif
```

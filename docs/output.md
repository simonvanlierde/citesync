# Output formats

`citesync check` and `citesync write` print text by default, as [check.md](check.md#findings-and-exit-codes) shows. The exit codes are the same for every format.

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

Findings are sorted by file, rule and field. `line` and `column` count from 1. `file` is null for a field no file holds. `term`, the CodeMeta term, is null for `unreadable` and `file-missing`. In the message, a value longer than 80 characters is cut short with `...`. JSON always lists every finding: `-q` and `-v` change only the text and GitHub output.

[tests/output.schema.json](../tests/output.schema.json) is the JSON Schema. A minor release may add rule ids and optional fields, so ignore what you don't know. Only a major release removes or retypes a field, and it bumps `version`.

## GitHub

`--format github` writes one workflow annotation per finding, titled `citesync <rule>`. A last notice counts them all, because GitHub shows only the first ten of each level.

## SARIF

`--format sarif` writes one SARIF 2.1.0 log. Each finding is a result with its `ruleId`, `level` (`error`, `warning`, or `note` for info), message and file. Like the text format, it leaves out info findings unless you pass `-v`. It always leaves out a finding on no file, because SARIF has nowhere to point it.

Upload it to GitHub code scanning with `github/codeql-action/upload-sarif`:

```yaml
- run: uvx citesync check --format sarif > citesync.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: citesync.sarif
```

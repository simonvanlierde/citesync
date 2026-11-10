# Output formats

`citesync check` and `citesync write` print text by default, as [check.md](check.md#findings-and-exit-codes) shows. The exit codes are the same for every format.

## JSON

`--format json` prints one document:

```json
{
  "schema_version": 1,
  "tool": { "name": "citesync", "version": "0.5.0" },
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
      "line": 3,
      "column": 3
    }
  ],
  "errors": []
}
```

`errors` is empty when the run finished. When citesync couldn't run (exit 3) or was interrupted (exit 130), the report has only `schema_version`, `tool` and `errors`, and stderr stays empty. Each error is an object with `message`, the line text output prints after `citesync:`, and `help`, what to do about it, or `null` when there is no known next step:

```json
{
  "schema_version": 1,
  "tool": { "name": "citesync", "version": "0.5.0" },
  "errors": [{ "message": "CITATION.cff: the source file is missing from /home/ada/radium; name another with --source, or the repo with --root", "help": null }]
}
```

A usage error (exit 2) is found before the run starts, so it prints the usage on stderr even with `--json`.

Findings are sorted by file, rule and field. `line` and `column` count from 1. For a finding on a field they point at the field's key, or at the table or object above it when the key isn't there under the name the mapping gives. For `unreadable` they point where the parser stopped, when it says. They are null where there is nothing to point at, such as a finding on no file, `file-missing`, `manifest-skipped` and `export-stale`. A list's key stands for the whole list, so an author finding points at `authors`, not at one author. A column counts characters, not bytes. `file` is null for a field no file holds. `term`, the CodeMeta term, is null for `unreadable`, `file-missing`, `manifest-skipped` and `export-stale`. In the message, a value longer than 80 characters is cut short with `...`. JSON always lists every finding: `-q` and `-v` change only the text, GitHub and SARIF output.

[tests/output.schema.json](../tests/output.schema.json) is the JSON Schema. A minor release may add rule ids and optional fields, so ignore what you don't know. Only a major release removes or retypes a field, and it bumps `schema_version`.

## GitHub

`--format github` writes one workflow annotation per finding, at the finding's line and column when it has them, titled `citesync <rule>`, with a `help:` line under the message. A last notice counts them all, because GitHub shows only the first ten of each level.

## SARIF

`--format sarif` writes one SARIF 2.1.0 log. Each finding is a result with its `ruleId`, `level` (`error`, `warning`, or `note` for info), message and file, and a `region` with `startLine` and `startColumn` when the finding has a line. Each rule carries its `help` text, which code scanning shows beside the alert. Like the text format, it leaves out info findings unless you pass `-v`, and warnings too with `-q`. It always leaves out a finding on no file, because SARIF has nowhere to point it.

Upload it to GitHub code scanning with `github/codeql-action/upload-sarif`:

```yaml
- run: uvx citesync check --format sarif > citesync.sarif
  continue-on-error: true
- uses: github/codeql-action/upload-sarif@v3
  with:
    sarif_file: citesync.sarif
```

# Configuration

citesync reads the first config it finds, in this order:

1. `citesync.toml`
2. `.citesync.toml`
3. `[tool.citesync]` in pyproject.toml
4. `[workspace.metadata.citesync]` or `[package.metadata.citesync]` in Cargo.toml
5. `"citesync"` in package.json

It ignores the others and doesn't merge them. `citesync config` prints the config in use and the file it came from.

```toml
source = "CITATION.cff"                  # any of the six files
codemeta-version = "3.0"                 # default: unset, so any CodeMeta version passes
files = ["codemeta.json", ".zenodo.json"]  # default: the citation files present
manifests = ["src/core/package.json"]      # replaces the default root manifests
write-manifests = ["keywords", "license"]  # or "all"; the manifest fields write may change
keywords-case-sensitive = true              # default false: keywords compare as names do
keywords-ignore-separators = true           # default false: big-data and big data stay a near miss (always equal against Cargo.toml)
ignore = ["description-mismatch"]          # rule ids whose findings to drop
```

`write-manifests` names fields by their CodeMeta term: `name`, `version`, `author`, `contributor`, `license`, `identifier` (the DOI), `codeRepository`, `description`, `keywords` and `datePublished`. This is the `term` in the JSON output. Rule ids use the plainer `doi`, `repository` and `date`.

With `codemeta-version` unset, `check` accepts CodeMeta 2.0, 3.0, 3.1 and 4.0, and `write` leaves `@context` alone. Once it's set, any other `@context` is a [`context-mismatch`](rules.md#context-mismatch) error, which `write` fixes.

An `ignore` entry that matched no finding prints a warning to stderr. An unknown rule id is a config error. You can't ignore `unreadable`.

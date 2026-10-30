# Configuration

Config goes in the first of `citesync.toml`, `.citesync.toml`, `[tool.citesync]` in pyproject.toml, `[workspace.metadata.citesync]` or `[package.metadata.citesync]` in Cargo.toml, or `"citesync"` in package.json. `citesync config` prints the config in use and the file it came from.

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

`write-manifests` names fields by their CodeMeta term, as the JSON `term` does: `name`, `version`, `author`, `contributor`, `license`, `identifier` (the DOI), `codeRepository`, `description`, `keywords` and `datePublished`. Rule ids use the plainer `doi`, `repository` and `date`. Manifests have no release date, so `datePublished` there changes nothing.

`codemeta-version` has no default. Unset, `check` accepts any CodeMeta version it reads (2.0, 3.0, 3.1, 4.0) and `write` leaves `@context` alone. Set, a codemeta.json with another `@context` is a [`context-mismatch`](rules.md#context-mismatch) error, which `write` fixes. A codemeta.json that `write` creates gets the configured version, else 3.0, the version Software Heritage reads.

An `ignore` entry that matched no finding prints a warning to stderr. An unknown rule id is a config error, and `unreadable` can't be ignored.

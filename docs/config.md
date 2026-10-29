# Configuration

Config goes in the first of `citesync.toml`, `.citesync.toml`, `[tool.citesync]` in pyproject.toml, `[workspace.metadata.citesync]` or `[package.metadata.citesync]` in Cargo.toml, or `"citesync"` in package.json. `citesync config` prints the config in use and the file it came from.

```toml
source = "CITATION.cff"                  # any of the six files
codemeta-version = "3.0"
files = ["codemeta.json", ".zenodo.json"]  # default: the citation files present
manifests = ["src/core/package.json"]      # replaces the default root manifests
write-manifests = ["keywords", "license"]  # or "all"; the manifest fields write may change
keywords-case-sensitive = true              # default false: keywords compare as names do
keywords-ignore-separators = true           # default false: big-data and big data stay a near miss (always equal against Cargo.toml)
ignore = ["description-mismatch"]          # rule ids whose findings to drop
```

`write-manifests` names fields by their CodeMeta term, as the JSON `term` does: `name`, `version`, `author`, `license`, `identifier` (the DOI), `codeRepository`, `description` and `keywords`. Rule ids use the plainer `doi` and `repository`.

An `ignore` entry that matched no finding prints a warning to stderr. An unknown rule id is a config error, and `unreadable` can't be ignored.

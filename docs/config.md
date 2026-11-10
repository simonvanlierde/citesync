# Configuration

citesync reads the first config it finds, in this order:

1. `citesync.toml`
2. `.citesync.toml`
3. `[tool.citesync]` in pyproject.toml
4. `[workspace.metadata.citesync]` or `[package.metadata.citesync]` in Cargo.toml
5. `"citesync"` in package.json

It ignores the others and doesn't merge them. `citesync config` prints the config in use, the file it came from and the repo root.

```toml
source = "CITATION.cff"                  # any supported source filename
codemeta-version = "3.0"                 # default: unset, so any CodeMeta version passes
files = ["codemeta.json", ".zenodo.json"]  # default: the citation files present
manifests = ["src/core/package.json"]      # replaces the default root manifests and dataset files
write-manifests = ["keywords", "license"]  # or "all"; the manifest fields write may change
exports = ["CITATION.bib", "schema.jsonld"]  # citations write keeps in step; the suffix picks the format
zenodo-contributor-type = "Other"          # default unset: new Zenodo contributors need a hand edit
keywords-case-sensitive = true              # default false: keywords compare as names do
keywords-ignore-separators = true           # default false: big-data and big data stay a near miss (always equal against Cargo.toml)
ignore = ["description-mismatch"]          # rule ids whose findings to drop
```

`write-manifests` takes the fields a manifest holds, by their CodeMeta term: `version`, `author`, `contributor`, `license`, `codeRepository` and `keywords`. `"all"` means those six. This is the `term` in the JSON output. Rule ids use the plainer `repository`, but `write-manifests` takes only the term, and says which one to use. Write never changes the other compared fields, `name`, `description`, `identifier` (the DOI), `swhid` (the Software Heritage identifier) and `datePublished`, in a manifest.

Quote `codemeta-version`: `3.0` without quotes is a TOML number. With `codemeta-version` unset, `check` accepts CodeMeta 2.0, 3.0, 3.1 and 4.0, and `write` leaves `@context` alone. Once it's set, any other `@context` is a [`context-mismatch`](rules.md#context-mismatch) error, which `write` fixes.

`exports` lists citation files made from the source: `.bib`, `.csl.json`, `.apa.txt`, `.jsonld`, `.datacite.xml`, `.ris` or `.enw`, relative to the repo root. [Citation exports](export.md) has the formats.

An `ignore` entry that matched no finding prints a warning to stderr, unless you pass `-q`. An unknown rule id is a config error, which suggests the closest rule id. You can't ignore `unreadable`.

`zenodo-contributor-type` supplies the type when creating new .zenodo.json contributors or adding people to an existing opted-in `contributors` list. It never changes an existing person's type or translates CRediT roles. To start an empty list, add `"contributors": []` to .zenodo.json. An absent list stays absent. An empty list in the source still means the source supplies no contributors.

Use one of [Zenodo's contributor types](https://developers.zenodo.org/#representation), with the same capitalization: `ContactPerson`, `DataCollector`, `DataCurator`, `DataManager`, `Distributor`, `Editor`, `HostingInstitution`, `Other`, `Producer`, `ProjectLeader`, `ProjectManager`, `ProjectMember`, `RegistrationAgency`, `RegistrationAuthority`, `RelatedPerson`, `ResearchGroup`, `RightsHolder`, `Researcher`, `Sponsor`, `Supervisor` or `WorkPackageLeader`.

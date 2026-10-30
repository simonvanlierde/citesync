"""The rules a finding can come from: id, severity, a one-line summary, what to do, and the details.

``docs/rules.md`` is generated from these: ``uv run python -m citesync.rules > docs/rules.md``.
"""

from dataclasses import dataclass

DOCS_URL = "https://github.com/simonvanlierde/citesync/blob/main/docs/rules.md"


@dataclass(frozen=True)
class Rule:
    """One rule. ``help`` says what to do about a finding; ``details`` how the rule compares."""

    severity: str
    summary: str
    help: str
    details: str


# Both keyword rules: what happens to a keyword that only spells its separators differently.
_SEPARATORS = (
    " A keyword that differs from the other file's only in separators (`big-data`, `big_data`, `big data`)"
    " is named in the message, and write gives it the source's spelling where it stands;"
    " `keywords-ignore-separators = true` makes such keywords equal. They are always equal against Cargo.toml,"
    " since crates.io refuses a keyword with a space."
)

_FIX = "Make the file agree with the source, or the other way round if the source is wrong."
_GAP = (
    " When the source has no place or no value for the field (pyproject.toml has no DOI),"
    " the other files that hold it must agree with each other."
)
# term: (rule id, summary, how the field compares)
_FIELDS = {
    "name": (
        "name-mismatch",
        "The title differs from the source's.",
        (
            "CFF `title` and CodeMeta and Zenodo `name`/`title` compare as written, with whitespace collapsed."
            " Manifests are not compared: a manifest `name` is a package id."
        ),
    ),
    "version": (
        "version-mismatch",
        "The version differs from the source's.",
        "Semver pre-release tags are read as PEP 440 first, so `0.3.1-rc.1` equals `0.3.1rc1`.",
    ),
    "author": (
        "author-mismatch",
        "The authors differ from the source's.",
        (
            "Citation files must list the same people in the same order, with equal ORCIDs where both have one."
            " Names compare case-insensitively after Unicode normalisation, and Zenodo's `Family, Given` and"
            " npm or Cargo `Name <email>` are read as names. Manifests are compared on names only, and npm's"
            " one `author` with the first author."
        ),
    ),
    "contributor": (
        "contributor-mismatch",
        "The contributors differ from the source's.",
        (
            "Compared as authors are: the same people in the same order, with equal ORCIDs where both have one."
            " Only the people count, never a CodeMeta Role or a Zenodo contributor `type`. CITATION.cff,"
            " pyproject.toml and Cargo.toml have no contributor list, and npm's `contributors` is compared on names."
        ),
    ),
    "license": (
        "license-mismatch",
        "The licence differs from the source's.",
        (
            "SPDX ids, SPDX URLs and Zenodo's lowercase ids are the same licence, compared case-insensitively."
            " A list of licences reads as `A OR B`."
        ),
    ),
    "identifier": (
        "doi-mismatch",
        "The DOI differs from the source's.",
        "DOIs compare case-insensitively, with or without `https://doi.org/`. Manifests have no DOI.",
    ),
    "codeRepository": (
        "repository-mismatch",
        "The repository URL differs from the source's.",
        (
            "`git+`, `.git` and a trailing slash are removed first, and npm shorthands and SSH remotes"
            " are read as https URLs."
        ),
    ),
    "description": (
        "description-mismatch",
        "The description differs from the source's.",
        (
            "Compared as written, with whitespace collapsed. Manifests are not compared: a manifest"
            " description is a one-line summary, not an abstract."
        ),
    ),
    "keywords": (
        "keywords-mismatch",
        "The keywords differ from the source's.",
        (
            "Citation files must hold the same keywords, in any order. A manifest's keywords are"
            " checked by `keywords-not-subset` instead." + _SEPARATORS
        ),
    ),
    "datePublished": (
        "date-mismatch",
        "The release date differs from the source's.",
        (
            "CFF `date-released`, CodeMeta `datePublished` and Zenodo `publication_date` compare as `YYYY-MM-DD`;"
            " a time after the date is ignored. Manifests have no release date."
        ),
    ),
}
MISMATCH = {term: rule for term, (rule, _, _) in _FIELDS.items()}

RULES = {
    **{rule: Rule("error", summary, _FIX, details + _GAP) for rule, summary, details in _FIELDS.values()},
    "keywords-not-subset": Rule(
        "error",
        "A manifest has a keyword the citation file doesn't.",
        "Add the keyword to the citation file, or remove it from the manifest.",
        "A manifest's keywords must all be in the citation file's, whichever of the two is the source:"
        " a citation file can hold more keywords than a registry allows (crates.io allows five)." + _SEPARATORS,
    ),
    "context-mismatch": Rule(
        "error",
        "codemeta.json's `@context` is not the configured CodeMeta version.",
        "Change the `@context` to the configured version, or set `codemeta-version` in the config.",
        "The configured version is `codemeta-version`. With it unset, the rule is silent: any version citesync"
        " reads passes, and citesync reads CodeMeta 2.0, 3.0, 3.1 and 4.0.",
    ),
    "role-dangling": Rule(
        "warning",
        "A CodeMeta Role in codemeta.json points at a person who isn't listed.",
        "Add the person back, point the Role at their ORCID, or remove the Role.",
        "A `Role` entry in codemeta.json's `author` or `contributor` list, as credit-matrix writes CRediT roles,"
        " names its person by ORCID in `schema:author`. The rule warns when no `Person` in either list has that"
        " ORCID as its `@id`, as after someone is replaced. The role itself is not checked, and `write` never"
        " changes a Role.",
    ),
    "version-behind-tag": Rule(
        "warning",
        "The source's version is older than the repo's newest git tag.",
        "Bump the version in the source and run `citesync write`, so the next release isn't cited as the last one.",
        "Tags are read from the `.git` directory of the repo holding the root, found by walking up from it, and"
        " those that read as a PEP 440 version count, with or without a leading `v`, so `v0.2.0` is newer than"
        " `0.1.0`. Outside a git repository, or when no tag reads as a version, the rule is silent. A warning, so"
        " `write` never changes the version for it.",
    ),
    "zenodo-license-list": Rule(
        "error",
        "CITATION.cff's `license` is a list, and Zenodo would refuse the release.",
        "Give one licence in CITATION.cff, or add a .zenodo.json, which Zenodo reads instead.",
        "When a repo has no .zenodo.json, Zenodo's GitHub integration reads CITATION.cff and loads its `license`"
        ' as one string, so a list, even of one licence, fails the release with "Citation metadata load failed".'
        " Checked only when no .zenodo.json sits beside CITATION.cff.",
    ),
    "zenodo-drops-field": Rule(
        "warning",
        "Zenodo won't carry this CITATION.cff field into the record.",
        "Add a .zenodo.json with the field's Zenodo form (`related_identifiers`, `references`) if the record needs it.",
        "Without a .zenodo.json, Zenodo reads CITATION.cff but leaves out `identifiers` and `references`: the"
        " DOI comes from the release and the version and date from the tag. Checked only when no .zenodo.json"
        " sits beside CITATION.cff.",
    ),
    "file-missing": Rule(
        "error",
        "A file listed under `files` doesn't exist.",
        "Run `citesync write`, which creates a missing codemeta.json; create any other file by hand, or take it off"
        " `files`.",
        "Only for a citation file named in the `files` setting: without that setting, citesync checks the citation"
        " files that are there. `citesync write` creates codemeta.json from the source, with the configured"
        " `codemeta-version`, else 3.0. It doesn't create a .zenodo.json, which a repo needs only for what CITATION.cff"
        " can't hold, or a CITATION.cff.",
    ),
    "unreadable": Rule(
        "error",
        "citesync could not read the file.",
        "Fix the file so its parser accepts it.",
        "The file resolves outside the repo root through a symlink, could not be opened, is not UTF-8, does not"
        " parse, has a top level that is not a mapping, holds a value of a shape its format doesn't allow, or is"
        " a format version citesync doesn't read (CFF other than 1.2.0, a codemeta.json whose `@context` is not"
        " CodeMeta). The finding gives the"
        " parser's message, and its line and column when the parser reports them. The other files are still"
        " checked against each other. When the unreadable file is the source, each field it has a place for is"
        " reported as `not-checked`. This rule can't be ignored.",
    ),
    "not-checked": Rule(
        "info",
        "A field was not compared.",
        "Add the field to the source if the files should carry it.",
        "Either no file holds a value for the field, or the source could not be read. Info only: it never"
        " changes the exit code, and text and GitHub output show it only with `--verbose`.",
    ),
}


def explain(rule: str) -> str:
    """The rule's section of ``docs/rules.md``."""
    r = RULES[rule]
    return f"## {rule}\n\n{r.summary} Severity: {r.severity}.\n\n{r.details}\n\nTo fix: {r.help}\n"


def markdown() -> str:
    """The whole of ``docs/rules.md``."""
    head = (
        "# Rules\n\n<!-- Generated from src/citesync/rules.py by"
        " `uv run python -m citesync.rules > docs/rules.md`. Edit that file, not this one. -->\n\n"
        "`citesync rules` lists these rules, and `citesync explain <id>` prints one section.\n"
    )
    return "\n".join([head, *map(explain, RULES)])


if __name__ == "__main__":
    print(markdown(), end="")  # noqa: T201

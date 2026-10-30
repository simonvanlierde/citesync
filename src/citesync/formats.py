"""Read each of the six files into one record keyed by CodeMeta terms.

The mapping says where a term sits. The adapters here only reshape what a path
can't express (Cargo workspace inheritance, npm strings that may be objects,
PEP 621 ``dynamic``), and the codecs in :mod:`citesync.codecs` read the spelling.
"""

import json
import re
import tomllib
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError, YAMLError

from citesync import codecs
from citesync.errors import CheckError, UnreadableError
from citesync.mapping import PEOPLE, PERSON_TERMS, TERMS, Mapping, person_terms, relative, resolve

CITATION_FILES = {"CITATION.cff": "cff-1.2.0", "codemeta.json": "codemeta", ".zenodo.json": "zenodo"}
MANIFESTS = {"pyproject.toml": "pep621", "Cargo.toml": "cargo", "package.json": "npm"}
FORMAT_OF = CITATION_FILES | MANIFESTS
CODEMETA_VERSIONS = ("2.0", "3.0", "3.1", "4.0")
CFF_VERSIONS = ("1.2.0",)

_CODEMETA_CONTEXT = re.compile(r"^https?://w3id\.org/codemeta/v?(\d+\.\d+)/?$")
_NPM_BARE_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
_URL_LABELS = {"source": "Source", "sourcecode": "Source", "repository": "Repository", "homepage": "Homepage"}
_TOML_AT = re.compile(r" \(at (?:line (\d+), column (\d+)|end of document)\)$")
_CODEMETA_2_DOI = "https://doi.org/10.5063/schema/codemeta-2.0"
_KEYWORD_COMMAS = re.compile("[,\uff0c\u3001]")  # ASCII, full-width and ideographic commas


@dataclass(frozen=True)
class Person:
    """One author. ``name`` is ``"Given Family"``; a format with one name string has no parts.

    ``organization`` marks a CFF entity or a CodeMeta Organization, written back as one; it never
    makes two authors differ.
    """

    name: str | None
    given: str | None = None
    family: str | None = None
    orcid: str | None = None
    organization: bool = field(default=False, compare=False)


def same_name(p: Person, q: Person) -> bool:
    """Equal names; a one-string name also matches the other's ``"Family Given"`` or ``"FamilyGiven"``.

    Two split names in the opposite order still differ: there the parts say which is the family name.
    """
    a, b = codecs.name_key(p.name or ""), codecs.name_key(q.name or "")
    if a == b:
        return True
    p_split, q_split = bool(p.given and p.family), bool(q.given and q.family)
    if p_split == q_split:
        return False
    split, one = (p, b) if p_split else (q, a)
    return one in {codecs.name_key(f"{split.family}{sep}{split.given}") for sep in (" ", "")}


@dataclass(frozen=True)
class Doc:
    """One file as citesync sees it.

    Attributes:
        path: Relative to the repo root, with ``/``.
        format: The mapping's format id.
        record: Term to normalised value; a term with no value is left out.
        slots: Terms and person sub-terms the format has a place for (a non-null mapping path).
        version: The detected format version (CFF and codemeta only).
        release: False for a manifest that isn't released: a pyproject.toml with no
            ``[build-system]``, a private package.json.
        readable: False for a file citesync couldn't read, whose record is empty.
        dangling_roles: For codemeta.json, (list, ORCID) for each Role whose person isn't listed.
        zenodo_gaps: For a CITATION.cff with no .zenodo.json beside it, (key, rule id) for each
            key Zenodo refuses or drops when it archives a release.
    """

    path: str
    format: str
    record: dict[str, Any]
    slots: frozenset[str]
    version: str | None
    release: bool
    readable: bool = True
    dangling_roles: tuple[tuple[str, str], ...] = ()
    zenodo_gaps: tuple[tuple[str, str], ...] = ()

    @property
    def is_citation(self) -> bool:
        """CITATION.cff, codemeta.json or .zenodo.json."""
        return self.format in CITATION_FILES.values()


def format_of(path: str) -> str:
    """The format id of a file, from its name.

    Raises:
        CheckError: when the name is none of the six files.
    """
    fmt = FORMAT_OF.get(PurePosixPath(path).name)
    if fmt is None:
        msg = f"{path}: not one of {', '.join(FORMAT_OF)}"
        raise CheckError(msg)
    return fmt


def inside(root: Path, rel: str) -> bool:
    """Whether ``rel`` resolves inside ``root``: a symlink may point anywhere in the repo, but not out of it."""
    return (root / rel).resolve().is_relative_to(root.resolve())


def read_doc(root: Path, rel: str, mapping: Mapping) -> Doc:
    """Read ``rel`` under ``root`` into its record.

    Raises:
        UnreadableError: when the file resolves outside ``root``, can't be read or parsed, has a format version
            citesync doesn't read, or has a key holding a shape its format doesn't allow.
    """
    fmt = format_of(rel)
    if not inside(root, rel):  # an untrusted clone could point it at any file the user can read
        raise UnreadableError(rel, "resolves outside the repo root")
    data = load(root / rel, rel)
    version = _detect_version(fmt, data, rel)
    release = _is_release(fmt, data)
    record, roles = {}, ()
    no_zenodo = not (root / rel).with_name(".zenodo.json").is_file()
    gaps = zenodo_gaps(data) if fmt == CITATION_FILES["CITATION.cff"] and no_zenodo else ()
    try:
        data = _adapt(fmt, data, root, rel)
        if fmt == "codemeta":
            roles = dangling_roles(data)
        for term in TERMS:
            path = mapping[fmt, term]
            if path is None:
                continue
            value = _read_term(fmt, term, data, path, mapping)
            if value is not None:
                record[term] = value
    except (AttributeError, TypeError) as err:  # a key holding a shape its format doesn't allow
        raise UnreadableError(rel, f"unexpected shape ({err})") from err
    return Doc(rel, fmt, record, slots(fmt, mapping), version, release, dangling_roles=roles, zenodo_gaps=gaps)


def zenodo_gaps(cff: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """The CITATION.cff keys Zenodo refuses or drops when it reads the file instead of a .zenodo.json.

    Zenodo loads ``license`` as one string, so a list fails the release, and it doesn't carry
    ``identifiers`` or ``references`` into the record (zenodo-rdm ``github/schemas.py``, 2026-10).
    A Zenodo DOI among the identifiers is no loss: Zenodo links its own records.
    """
    gaps = [("license", "zenodo-license-list")] if isinstance(cff.get("license"), list) else []
    ids = [i for i in cff.get("identifiers") or [] if not _zenodo_doi(i)]
    dropped = {"identifiers": ids, "references": cff.get("references")}
    return (*gaps, *((key, "zenodo-drops-field") for key, held in dropped.items() if held))


def _zenodo_doi(identifier: object) -> bool:
    return isinstance(identifier, dict) and "10.5281/zenodo." in str(identifier.get("value", "")).casefold()


def dangling_roles(data: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    """Each CodeMeta Role in ``author`` or ``contributor`` whose ``schema:author`` ORCID no listed Person has.

    A Role names its person by ORCID (credit-matrix writes CRediT roles this way); a Role
    with no ORCID there is skipped. The Role itself is never read.
    """
    entries = [
        (key, entry)
        for key in ("author", "contributor")
        for entry in (data[key] if isinstance(data.get(key), list) else [data.get(key)])
        if isinstance(entry, dict)
    ]
    people = {codecs.orcid_decode(_ld(e, "id")) for _, e in entries if _ld(e, "type") != "Role"}
    found = []
    for key, entry in entries:
        target = entry.get("schema:author")
        orcid = codecs.orcid_decode(_ld(target, "id") if isinstance(target, dict) else target)
        if _ld(entry, "type") == "Role" and orcid and orcid not in people:
            found.append((key, orcid))
    return tuple(found)


def _ld(node: dict[str, Any], key: str) -> object:
    """``node``'s ``@type`` or ``@id``, or the ``type`` or ``id`` that CodeMeta 3's context makes an alias of it."""
    return node.get(f"@{key}", node.get(key))


def slots(fmt: str, mapping: Mapping) -> frozenset[str]:
    """The terms and person sub-terms ``fmt`` has a place for."""
    return frozenset(term for term in TERMS + PERSON_TERMS if mapping[fmt, term] is not None)


def load(path: Path, rel: str) -> dict[str, Any]:  # noqa: C901 - one branch per way a file fails
    """Parse the TOML, JSON or YAML file at ``path``, named ``rel`` in errors.

    Raises:
        UnreadableError: when it can't be read or parsed, or its top level isn't a mapping.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise UnreadableError(rel, f"cannot read: {err.strerror}") from err
    except UnicodeDecodeError as err:
        raise UnreadableError(rel, f"not UTF-8 at byte {err.start}") from err
    if text.startswith("\ufeff") and path.suffix in {".json", ".toml"}:  # YAML skips one; JSON and TOML refuse it
        raise UnreadableError(rel, "starts with a byte order mark: save it as UTF-8 without one")
    try:
        if path.suffix == ".toml":
            data = tomllib.loads(text)
        elif path.suffix == ".json":
            data = json.loads(text)
        else:
            data = YAML(typ="base").load(text)  # every scalar a string: version 1.10 is not the float 1.1
    except json.JSONDecodeError as err:
        raise UnreadableError(rel, err.msg, err.lineno, err.colno) from err
    except tomllib.TOMLDecodeError as err:  # its position is only in the message before Python 3.14
        match = _TOML_AT.search(str(err))
        line, column = (int(match[1]), int(match[2])) if match and match[1] else (None, None)
        raise UnreadableError(rel, _TOML_AT.sub("", str(err)), line, column) from err
    except MarkedYAMLError as err:
        mark = err.problem_mark
        raise UnreadableError(rel, err.problem or str(err), mark and mark.line + 1, mark and mark.column + 1) from err
    except YAMLError as err:
        raise UnreadableError(rel, str(err)) from err
    if not isinstance(data, dict):
        raise UnreadableError(rel, "the top level is not a mapping")
    return data


def codemeta_version(context: object) -> str | None:
    """The CodeMeta version named in an ``@context`` string or list, or None."""
    for item in context if isinstance(context, list) else [context]:
        if item == _CODEMETA_2_DOI:
            return "2.0"
        if isinstance(item, str) and (match := _CODEMETA_CONTEXT.match(item)):
            return match[1]
    return None


def _detect_version(fmt: str, data: dict[str, Any], rel: str) -> str | None:
    if fmt == "codemeta":
        version = codemeta_version(data.get("@context"))
        if version not in CODEMETA_VERSIONS:
            msg = f"@context {data.get('@context')!r} is not CodeMeta {', '.join(CODEMETA_VERSIONS)}"
            raise UnreadableError(rel, msg)
        return version
    if fmt == "cff-1.2.0":
        version = str(data.get("cff-version"))
        if version not in CFF_VERSIONS:
            raise UnreadableError(rel, f"cff-version {data.get('cff-version')!r}, citesync reads 1.2.0")
        return version
    return None


def _is_release(fmt: str, data: dict[str, Any]) -> bool:
    if fmt == "pep621":
        return "build-system" in data
    if fmt == "npm":
        return data.get("private") is not True
    return True


def _adapt(fmt: str, data: dict[str, Any], root: Path, rel: str) -> dict[str, Any]:
    if fmt == "cargo":
        return _adapt_cargo(data, root, rel)
    if fmt == "pep621" and isinstance(project := data.get("project"), dict):
        dynamic = set(project.get("dynamic", []))  # a dynamic field is skipped, the rest still checked
        return {**data, "project": {k: v for k, v in project.items() if k not in dynamic}}
    if fmt == "npm":
        return _adapt_npm(data)
    if fmt == "codemeta":
        data = dict(data)
        for key in PEOPLE:
            if isinstance(people := data.get(key), dict):  # JSON-LD allows one node for a list of one
                data[key] = [people]
    return data


def locate(fmt: str, term: str, data: Any, path: str) -> tuple[Any, str] | None:  # noqa: ANN401
    """(container, key) of the value ``term`` reads at ``path``: the first alternative that has one.

    A blank value (null, ``""``, ``[]``) counts as none, so CFF's ``doi: ""`` gives way to ``identifiers``.
    Shared by the reader and the writer, so both pick the same value. A Cargo virtual workspace
    holds its fields in ``[workspace.package]``; a PEP 621 url label matches as packaging normalises
    it, the exact label first; Zenodo's isSupplementTo also lists papers by DOI and SWHIDs, which are skipped.
    """
    if fmt == "cargo" and "package" not in data:
        data = {"package": data.get("workspace", {}).get("package", {})}
    for alternative in path.split(" | "):
        parent, _, key = alternative.rpartition(".")
        key = key.removesuffix("[]")
        for node in resolve(data, parent) if parent else [data]:
            if not isinstance(node, dict):
                continue
            label = key if key in node else next((k for k in node if url_label(k) == key), None)
            if label is None or node[label] in (None, "", []):
                continue
            if term == "codeRepository" and (codecs.doi_decode(node[label]) or codecs.swhid_decode(node[label])):
                continue
            return node, label
    return None


def url_label(label: str) -> str | None:
    """A PEP 621 url label normalised as packaging does (``Source Code`` and ``source-code`` are ``Source``)."""
    return _URL_LABELS.get("".join(c for c in label.lower() if c.isalnum()))


def cff_person(author: dict[str, Any]) -> dict[str, Any]:
    """Fold ``name-particle`` and ``name-suffix`` into the family name, and read an entity's ``name`` as one.

    So CFF's (Simon, van, Lierde) reads as Zenodo's ``"van Lierde, Simon"`` does.
    """
    family = author.get("family-names") or (author.get("name") if "given-names" not in author else None)
    parts = [author.get("name-particle"), family, author.get("name-suffix")]
    family = " ".join(p for p in parts if isinstance(p, str) and p.strip()) or None
    return {**author, "family-names": family} if family else author


def codemeta_person(author: object) -> object:
    """Read a codemeta author with only a ``name``, such as an Organization, as a family name, as CFF's entity is."""
    if (
        isinstance(author, dict)
        and isinstance(author.get("name"), str)
        and not {"givenName", "familyName"} & author.keys()
    ):
        return {**author, "familyName": author["name"]}
    return author


def _adapt_npm(data: dict[str, Any]) -> dict[str, Any]:
    """Read npm's repository object or shorthand as a URL."""
    data = dict(data)
    if isinstance(data.get("repository"), dict):
        data["repository"] = data["repository"].get("url")
    if isinstance(data.get("repository"), str) and _NPM_BARE_REPO.match(data["repository"]):
        data["repository"] = f"github:{data['repository']}"  # npm reads a bare owner/repo as GitHub
    return data


def _adapt_cargo(data: dict[str, Any], root: Path, rel: str) -> dict[str, Any]:
    """Present a crate or a virtual workspace as ``package``, with ``.workspace = true`` keys resolved."""
    workspace = data if "workspace" in data else _find_workspace(root, rel)
    inherited = workspace.get("workspace", {}).get("package", {}) if workspace else {}
    package = data.get("package")
    if package is None:
        return {**data, "package": dict(inherited)}  # a virtual workspace reads as its [workspace.package]
    resolved = {}
    for key, value in package.items():
        if not (isinstance(value, dict) and value.get("workspace") is True):
            resolved[key] = value
        elif key in inherited:
            resolved[key] = inherited[key]
    return {**data, "package": resolved}


def _find_workspace(root: Path, rel: str) -> dict[str, Any] | None:
    """The nearest Cargo.toml above ``rel`` with a ``[workspace]``, inside the repo root."""
    for parent in PurePosixPath(rel).parents[1:]:
        candidate = root / parent / "Cargo.toml"
        if candidate.is_file() and inside(root, str(parent / "Cargo.toml")):
            data = load(candidate, str(parent / "Cargo.toml"))
            if "workspace" in data:
                return data
    return None


def _read_term(fmt: str, term: str, data: dict[str, Any], path: str, mapping: Mapping) -> Any:  # noqa: ANN401
    if term in PEOPLE:
        people = tuple(p for p in (person(fmt, el, path, mapping, term) for el in resolve(data, path)) if p)
        return people or None
    slot = locate(fmt, term, data, path)
    if slot is None:
        return None
    raw = slot[0][slot[1]]
    if term == "keywords":
        items = (
            raw
            if isinstance(raw, list)
            else _KEYWORD_COMMAS.split(raw)
            if fmt == "codemeta" and isinstance(raw, str)
            else [raw]
        )
        words = tuple(codecs.clean(w) for w in items if isinstance(w, str) and w.strip())
        return words or None
    if term in {"name", "description"}:  # in NFC, as names are, so equal text never differs by its encoding
        return (codecs.clean(unicodedata.normalize("NFC", raw)) or None) if isinstance(raw, str) else None
    return _DECODE[term](raw)


_DECODE = {
    "version": codecs.version_decode,
    "license": codecs.license_decode,
    "identifier": codecs.doi_decode,
    "swhid": codecs.swhid_decode,
    "codeRepository": codecs.repo_decode,
    "datePublished": codecs.date_decode,
}


def person(fmt: str, element: object, parent: str, mapping: Mapping, term: str) -> Person | None:
    """The person in ``element``, one entry of ``term``'s list at ``parent``; None when it has no name or ORCID.

    Check and write both read people here, so they match people the same way.
    """
    if fmt == "cff-1.2.0" and isinstance(element, dict):
        element = cff_person(element)
    elif fmt == "codemeta":
        element = codemeta_person(element)
    elif fmt == "npm" and isinstance(element, str):  # "Name <email>"
        element = {"name": element}
    given_term, family_term, orcid_term = person_terms(term)

    def sub(term: str) -> object:
        path = mapping[fmt, term]
        if path is None:
            return None
        rel = relative(path, parent)
        values = [element] if rel == "" else resolve(element, rel)
        return values[0] if values else None

    def text(value: object) -> str | None:
        return (codecs.clean(value) or None) if isinstance(value, str) else None

    orcid = codecs.orcid_decode(sub(orcid_term))
    given, family = None, None
    if mapping[fmt, given_term] == mapping[fmt, family_term]:
        raw = sub(given_term)
        if fmt == "zenodo":
            given, family = codecs.zenodo_name_decode(raw) or (None, None)
            name = codecs.display_name(given, family)
        else:
            name = codecs.contact_name_decode(raw)
    else:
        given, family = text(sub(given_term)), text(sub(family_term))
        name = codecs.display_name(given, family)
    if name is None and orcid is None:
        return None
    org = isinstance(element, dict) and (
        _ld(element, "type") == "Organization"
        if fmt == "codemeta"
        else fmt == "cff-1.2.0" and "given-names" not in element and "name" in element
    )
    return Person(name, given, family, orcid, organization=org)

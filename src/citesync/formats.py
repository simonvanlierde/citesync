"""Read each of the six files into one record keyed by CodeMeta terms.

The mapping says where a term sits. The adapters here only reshape what a path
can't express (Cargo workspace inheritance, npm strings that may be objects,
PEP 621 ``dynamic``), and the codecs in :mod:`citesync.codecs` read the spelling.
"""

import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from ruamel.yaml import YAML
from ruamel.yaml.error import MarkedYAMLError, YAMLError

from citesync import codecs
from citesync.errors import CheckError, UnreadableError
from citesync.mapping import PERSON_TERMS, TERMS, Mapping, relative, resolve

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


@dataclass(frozen=True)
class Person:
    """One author. ``name`` is ``"Given Family"``; a format with one name string has no parts."""

    name: str | None
    given: str | None = None
    family: str | None = None
    orcid: str | None = None


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
    """

    path: str
    format: str
    record: dict[str, Any]
    slots: frozenset[str]
    version: str | None
    release: bool
    readable: bool = True

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


def read_doc(root: Path, rel: str, mapping: Mapping) -> Doc:
    """Read ``rel`` under ``root`` into its record.

    Raises:
        UnreadableError: when the file can't be read or parsed, has a format version
            citesync doesn't read, or has a key holding a shape its format doesn't allow.
    """
    fmt = format_of(rel)
    data = load(root / rel, rel)
    version = _detect_version(fmt, data, rel)
    release = _is_release(fmt, data)
    record = {}
    try:
        data = _adapt(fmt, data, root, rel)
        for term in TERMS:
            path = mapping[fmt, term]
            if path is None:
                continue
            value = _read_term(fmt, term, data, path, mapping)
            if value is not None:
                record[term] = value
    except (AttributeError, TypeError) as err:  # a key holding a shape its format doesn't allow
        raise UnreadableError(rel, f"unexpected shape ({err})") from err
    return Doc(rel, fmt, record, slots(fmt, mapping), version, release)


def slots(fmt: str, mapping: Mapping) -> frozenset[str]:
    """The terms and person sub-terms ``fmt`` has a place for."""
    return frozenset(term for term in TERMS + PERSON_TERMS if mapping[fmt, term] is not None)


def load(path: Path, rel: str) -> dict[str, Any]:
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
        project = {k: v for k, v in project.items() if k not in dynamic}
        if isinstance(urls := project.get("urls"), dict):
            project["urls"] = _url_labels(urls)
        return {**data, "project": project}
    if fmt == "cff-1.2.0" and isinstance(data.get("authors"), list):
        return {**data, "authors": [_cff_person(a) if isinstance(a, dict) else a for a in data["authors"]]}
    if fmt == "npm":
        data = dict(data)
        if isinstance(data.get("author"), str):
            data["author"] = {"name": data["author"]}
        if isinstance(data.get("repository"), dict):
            data["repository"] = data["repository"].get("url")
        if isinstance(data.get("repository"), str) and _NPM_BARE_REPO.match(data["repository"]):
            data["repository"] = f"github:{data['repository']}"  # npm reads a bare owner/repo as GitHub
        return data
    if fmt == "codemeta" and isinstance(data.get("author"), dict):
        return {**data, "author": [data["author"]]}  # JSON-LD allows one node for a list of one
    return data


def _url_labels(urls: dict[str, Any]) -> dict[str, Any]:
    """PEP 621 url labels normalised as packaging does (``Source Code`` and ``source-code`` are ``Source``)."""
    named = dict(urls)
    for label, url in urls.items():
        known = _URL_LABELS.get("".join(c for c in label.lower() if c.isalnum()))
        if known:
            named.setdefault(known, url)
    return named


def _cff_person(author: dict[str, Any]) -> dict[str, Any]:
    """Fold ``name-particle`` and ``name-suffix`` into the family name, and read an entity's ``name`` as one.

    So CFF's (Simon, van, Lierde) reads as Zenodo's ``"van Lierde, Simon"`` does.
    """
    family = author.get("family-names") or (author.get("name") if "given-names" not in author else None)
    parts = [author.get("name-particle"), family, author.get("name-suffix")]
    family = " ".join(p for p in parts if isinstance(p, str) and p.strip()) or None
    return {**author, "family-names": family} if family else author


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
        if candidate.is_file():
            data = load(candidate, str(parent / "Cargo.toml"))
            if "workspace" in data:
                return data
    return None


def _read_term(fmt: str, term: str, data: dict[str, Any], path: str, mapping: Mapping) -> Any:  # noqa: ANN401
    values = resolve(data, path)
    if term == "author":
        people = tuple(p for p in (_person(fmt, el, path, mapping) for el in values) if p)
        return people or None
    if not values:
        return None
    if term == "codeRepository":  # Zenodo's isSupplementTo also lists papers by DOI
        values = [v for v in values if codecs.doi_decode(v) is None] or [None]
    raw = values[0]
    if term == "keywords":
        items = raw if isinstance(raw, list) else [raw]
        words = tuple(codecs.clean(w) for w in items if isinstance(w, str) and w.strip())
        return words or None
    if term in {"name", "description"}:
        return (codecs.clean(raw) or None) if isinstance(raw, str) else None
    return _DECODE[term](raw)


_DECODE = {
    "version": codecs.version_decode,
    "license": codecs.license_decode,
    "identifier": codecs.doi_decode,
    "codeRepository": codecs.repo_decode,
}


def _person(fmt: str, element: object, parent: str, mapping: Mapping) -> Person | None:
    def sub(term: str) -> object:
        path = mapping[fmt, term]
        if path is None:
            return None
        rel = relative(path, parent)
        values = [element] if rel == "" else resolve(element, rel)
        return values[0] if values else None

    def text(value: object) -> str | None:
        return (codecs.clean(value) or None) if isinstance(value, str) else None

    orcid = codecs.orcid_decode(sub("author.@id"))
    given, family = None, None
    if mapping[fmt, "author.givenName"] == mapping[fmt, "author.familyName"]:
        raw = sub("author.givenName")
        if fmt == "zenodo":
            given, family = codecs.zenodo_name_decode(raw) or (None, None)
            name = codecs.display_name(given, family)
        else:
            name = codecs.contact_name_decode(raw)
    else:
        given, family = text(sub("author.givenName")), text(sub("author.familyName"))
        name = codecs.display_name(given, family)
    if name is None and orcid is None:
        return None
    return Person(name, given, family, orcid)

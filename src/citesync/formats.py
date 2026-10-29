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
from ruamel.yaml.error import YAMLError

from citesync import codecs
from citesync.errors import CheckError
from citesync.mapping import TERMS, Mapping, relative, resolve

CITATION_FILES = {"CITATION.cff": "cff-1.2.0", "codemeta.json": "codemeta", ".zenodo.json": "zenodo"}
MANIFESTS = {"pyproject.toml": "pep621", "Cargo.toml": "cargo", "package.json": "npm"}
FORMAT_OF = CITATION_FILES | MANIFESTS
CODEMETA_VERSIONS = ("2.0", "3.0", "3.1", "4.0")
CFF_VERSIONS = ("1.2.0",)

_CODEMETA_CONTEXT = re.compile(r"^https?://w3id\.org/codemeta/v?(\d+\.\d+)/?$")
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
        slots: Terms the format has a place for (a non-null mapping path).
        version: The detected format version (CFF and codemeta only).
        release: False for a manifest that isn't released: a pyproject.toml with no
            ``[build-system]``, a private package.json.
    """

    path: str
    format: str
    record: dict[str, Any]
    slots: frozenset[str]
    version: str | None
    release: bool

    @property
    def is_citation(self) -> bool:
        """CITATION.cff, codemeta.json or .zenodo.json."""
        return self.format in CITATION_FILES.values()


def format_of(path: str) -> str | None:
    """The format id of a file, from its name."""
    return FORMAT_OF.get(PurePosixPath(path).name)


def read_doc(root: Path, rel: str, mapping: Mapping) -> Doc:
    """Read ``rel`` under ``root`` into its record.

    Raises:
        CheckError: when the file can't be read or parsed, or has a format version
            citesync doesn't read.
    """
    fmt = format_of(rel)
    if fmt is None:
        msg = f"{rel}: not one of {', '.join(FORMAT_OF)}"
        raise CheckError(msg)
    data = _load(root / rel, rel)
    version = _detect_version(fmt, data, rel)
    release = _is_release(fmt, data)
    data = _adapt(fmt, data, root, rel)
    record = {}
    for term in TERMS:
        path = mapping[fmt, term]
        if path is None:
            continue
        value = _read_term(fmt, term, data, path, mapping)
        if value is not None:
            record[term] = value
    slots = frozenset(term for term in TERMS if mapping[fmt, term] is not None)
    return Doc(rel, fmt, record, slots, version, release)


def _load(path: Path, rel: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        msg = f"{rel}: cannot read: {err.strerror}"
        raise CheckError(msg) from err
    except UnicodeDecodeError as err:
        msg = f"{rel}: cannot read: not UTF-8 at byte {err.start}"
        raise CheckError(msg) from err
    try:
        if path.suffix == ".toml":
            data = tomllib.loads(text)
        elif path.suffix == ".json":
            data = json.loads(text)
        else:
            data = YAML(typ="rt").load(text)
    except (tomllib.TOMLDecodeError, json.JSONDecodeError, YAMLError) as err:
        msg = f"{rel}: cannot parse: {err}"
        raise CheckError(msg) from err
    if not isinstance(data, dict):
        msg = f"{rel}: the top level is not a mapping"
        raise CheckError(msg)
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
            msg = f"{rel}: @context {data.get('@context')!r} is not CodeMeta {', '.join(CODEMETA_VERSIONS)}"
            raise CheckError(msg)
        return version
    if fmt == "cff-1.2.0":
        version = str(data.get("cff-version"))
        if version not in CFF_VERSIONS:
            msg = f"{rel}: cff-version {data.get('cff-version')!r}, citesync reads 1.2.0"
            raise CheckError(msg)
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
        data = dict(data)
        if isinstance(data.get("author"), str):
            data["author"] = {"name": data["author"]}
        if isinstance(data.get("repository"), dict):
            data["repository"] = data["repository"].get("url")
        return data
    if fmt == "codemeta" and isinstance(data.get("author"), dict):
        return {**data, "author": [data["author"]]}  # JSON-LD allows one node for a list of one
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
        if candidate.is_file():
            data = _load(candidate, str(parent / "Cargo.toml"))
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
    raw = values[0]
    if term == "keywords":
        items = raw if isinstance(raw, list) else [raw]
        words = tuple(" ".join(str(w).split()) for w in items if isinstance(w, str) and w.strip())
        return words or None
    if term in {"name", "description"}:
        return (" ".join(raw.split()) or None) if isinstance(raw, str) else None
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
        return (" ".join(value.split()) or None) if isinstance(value, str) else None

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

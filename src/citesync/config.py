"""Find and validate the config: the first location found wins, flags override it."""

import json
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from citesync.errors import CheckError, UnreadableError, did_you_mean
from citesync.formats import (
    CITATION_FILES,
    CODEMETA_VERSIONS,
    DATASET_FILES,
    FORMAT_OF,
    MANIFESTS,
    format_of,
    inside,
    load,
    slots,
)
from citesync.mapping import TERMS, load_mapping, resolve
from citesync.rules import MISMATCH, RULES


@dataclass(frozen=True)
class Config:
    """The settings a check runs with. ``None`` for files or manifests means the default discovery.

    ``codemeta_version`` None means any CodeMeta version citesync reads passes.
    """

    source: str = "CITATION.cff"
    codemeta_version: str | None = None
    files: tuple[str, ...] | None = None
    manifests: tuple[str, ...] | None = None
    write_manifests: tuple[str, ...] = ()
    exports: tuple[str, ...] = ()
    zenodo_contributor_type: str | None = None
    keywords_case_sensitive: bool = False
    keywords_ignore_separators: bool = False
    ignore: tuple[str, ...] = ()
    origin: str = "defaults"
    required_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()


# Config tables inside manifests, in the order docs/config.md lists them: (file, mapping path, origin).
_MANIFEST_TABLES = (
    ("pyproject.toml", "tool.citesync", "pyproject.toml [tool.citesync]"),
    ("Cargo.toml", "workspace.metadata.citesync", "Cargo.toml [workspace.metadata.citesync]"),
    ("Cargo.toml", "package.metadata.citesync", "Cargo.toml [package.metadata.citesync]"),
    ("package.json", "citesync", 'package.json "citesync"'),
)


def find_config(root: Path) -> tuple[dict[str, Any], str]:
    """The raw config table and where it came from, in the order docs/config.md lists; ``({}, "defaults")`` when none.

    A manifest that can't be read, or has a non-table on the way to the config table,
    holds no config here: the check reports it as ``unreadable`` if it is broken.
    """
    for name in ("citesync.toml", ".citesync.toml"):
        if (root / name).is_file():
            return load(root / name, name), name
    for name, path, origin in _MANIFEST_TABLES:
        if (root / name).is_file():
            try:
                table = next(iter(resolve(load(root / name, name), path)), None)
            except UnreadableError:
                continue
            if table is not None:
                return table, origin
    return {}, "defaults"


def find_root(start: Path) -> Path:
    """The nearest directory from ``start`` up that holds a citation file or a citesync config.

    The walk stops at the directory holding ``.git``, so a submodule or nested repo never takes its parent's files,
    and returns that directory when it found nothing; outside a git repo, ``start``.
    """
    for directory in (start, *start.parents):
        names = (*CITATION_FILES, "citesync.toml", ".citesync.toml")
        if any((directory / name).is_file() for name in names) or find_config(directory)[1] != "defaults":
            return directory
        if _is_repo(directory):
            return directory
    return start


def git_top(start: Path) -> Path | None:
    """The nearest directory from ``start`` up that holds ``.git``: the top of its repo, or None outside one."""
    start = start.resolve()
    return next((directory for directory in (start, *start.parents) if _is_repo(directory)), None)


def _is_repo(directory: Path) -> bool:
    """Whether ``directory`` holds a ``.git`` git would accept: a folder with ``HEAD``, or a submodule's file."""
    git = directory / ".git"
    return (git / "HEAD").is_file() or git.is_file()


def load_config(root: Path, source: str | None = None) -> Config:
    """The config in use under ``root``, with ``source`` from the command line on top.

    Raises:
        CheckError: on an unknown key or a value citesync can't use.
    """
    raw, origin = find_config(root)
    if not isinstance(raw, dict):
        msg = f"{origin}: the citesync config is not a table"
        raise CheckError(msg)
    unknown = sorted(set(raw) - set(_PARSE))
    if unknown:
        msg = f"{origin}: unknown key {', '.join(unknown)}; known keys: {', '.join(_PARSE)}"
        raise CheckError(msg)
    config = Config(origin=origin, **{key.replace("-", "_"): _PARSE[key](value, origin) for key, value in raw.items()})
    for path, _ in config.required_fields:
        if not inside(root, path):
            msg = f"{origin}: required-fields path {path!r} resolves outside the repo root"
            raise CheckError(msg)
    if source is not None:
        config = replace(config, source=_path(source, FORMAT_OF, "--source", "source"))
    return config


def _codemeta_version(value: object, origin: str) -> str:
    if isinstance(value, float):  # TOML reads an unquoted 3.0 as a number
        msg = f'{origin}: codemeta-version must be a string, such as "{value}"'
        raise CheckError(msg)
    if value not in CODEMETA_VERSIONS:
        msg = f"{origin}: codemeta-version must be one of {', '.join(CODEMETA_VERSIONS)}"
        raise CheckError(msg)
    return str(value)


# Zenodo deposition metadata: https://developers.zenodo.org/#representation
ZENODO_CONTRIBUTOR_TYPES = (
    "ContactPerson",
    "DataCollector",
    "DataCurator",
    "DataManager",
    "Distributor",
    "Editor",
    "HostingInstitution",
    "Other",
    "Producer",
    "ProjectLeader",
    "ProjectManager",
    "ProjectMember",
    "RegistrationAgency",
    "RegistrationAuthority",
    "RelatedPerson",
    "ResearchGroup",
    "RightsHolder",
    "Researcher",
    "Sponsor",
    "Supervisor",
    "WorkPackageLeader",
)


def _zenodo_contributor_type(value: object, origin: str) -> str:
    if not isinstance(value, str) or value not in ZENODO_CONTRIBUTOR_TYPES:
        msg = f"{origin}: zenodo-contributor-type must be one of {', '.join(ZENODO_CONTRIBUTOR_TYPES)}"
        raise CheckError(msg)
    return value


def _bool(value: object, origin: str, key: str) -> bool:
    if not isinstance(value, bool):
        msg = f"{origin}: {key} must be true or false"
        raise CheckError(msg)
    return value


def _path(value: object, names: dict[str, str], origin: str, key: str) -> str:
    if not isinstance(value, str) or PurePosixPath(value).name not in names:
        msg = f"{origin}: {key} must name one of {', '.join(names)}, got {value!r}"
        raise CheckError(msg)
    return _relative(value, origin, key)


def _relative(value: str, origin: str, key: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        msg = f"{origin}: {key} {value!r} must be relative to the repo root, inside it"
        raise CheckError(msg)
    return str(path)


def _paths(value: object, names: dict[str, str], origin: str, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        msg = f"{origin}: {key} must be a list of paths"
        raise CheckError(msg)
    return tuple(_path(item, names, origin, key) for item in value)


# The terms a manifest holds and write may change there: what "all" means in write-manifests.
MANIFEST_TERMS = ("version", "author", "contributor", "license", "codeRepository", "keywords")
# Rule ids name a few terms more plainly; write-manifests takes only the term.
_RULE_NAMES = {rule.removesuffix("-mismatch"): term for term, rule in MISMATCH.items()}


def _write_manifests(value: object, origin: str) -> tuple[str, ...]:
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not all(isinstance(i, str) for i in items):
        msg = f"{origin}: write-manifests must be 'all' or a list of {', '.join(MANIFEST_TERMS)}, got {value!r}"
        raise CheckError(msg)
    for item in items:
        if item == "all" or item in MANIFEST_TERMS:
            continue
        term, hint = _RULE_NAMES.get(item, item), ""
        if term in MANIFEST_TERMS:
            why = f"{item!r} is {term} here"
        elif term in TERMS:
            why = f"{item!r} is never written to a manifest"
        else:
            why, hint = f"{item!r} is not a term", did_you_mean(item, MANIFEST_TERMS)
        msg = f"{origin}: write-manifests: {why}; it takes 'all' or {', '.join(MANIFEST_TERMS)}{hint}"
        raise CheckError(msg)
    return MANIFEST_TERMS if "all" in items else tuple(items)


def _exports(value: object, origin: str) -> tuple[str, ...]:
    from citesync.export import SUFFIXES, format_of  # noqa: PLC0415 - only when a config lists exports

    if not isinstance(value, list):
        msg = f"{origin}: exports must be a list of paths"
        raise CheckError(msg)
    for item in value:
        if not isinstance(item, str) or format_of(item) is None:
            msg = f"{origin}: exports entry {item!r} must end in one of {', '.join(SUFFIXES)}"
            raise CheckError(msg)
    return tuple(dict.fromkeys(_relative(item, origin, "exports") for item in value))


def _required_fields(value: object, origin: str) -> tuple[tuple[str, tuple[str, ...]], ...]:
    """Validate named record terms against the pinned format's slots."""
    if not isinstance(value, dict):
        msg = f"{origin}: required-fields must be a table of paths to lists of CodeMeta terms"
        raise CheckError(msg)
    required = {}
    mapping = load_mapping()
    for path, terms in value.items():
        rel = _path(path, FORMAT_OF, origin, "required-fields")
        if "\\" in path or ":" in path or not path.isprintable():
            msg = f"{origin}: required-fields path {path!r} must be a printable relative POSIX path"
            raise CheckError(msg)
        if not isinstance(terms, list) or not terms or not all(isinstance(term, str) for term in terms):
            msg = f"{origin}: required-fields {path!r} must be a non-empty list of CodeMeta terms"
            raise CheckError(msg)
        for term in terms:
            if term not in TERMS:
                msg = f"{origin}: required-fields: {term!r} is not a supported term; choose from {', '.join(TERMS)}"
                raise CheckError(msg)
            if term not in slots(format_of(rel), mapping):
                msg = f"{origin}: required-fields: {path!r} cannot represent {term!r} in the pinned mapping"
                raise CheckError(msg)
        required[rel] = tuple(dict.fromkeys((*required.get(rel, ()), *terms)))
    return tuple(required.items())


def _ignore(value: object, origin: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(i, str) for i in value):
        msg = f"{origin}: ignore must be a list of rule ids, got {value!r}"
        raise CheckError(msg)
    for rule in value:
        if rule == "unreadable":
            msg = f"{origin}: ignore entry 'unreadable' can't be ignored: a file citesync can't read always fails"
            raise CheckError(msg)
        if rule not in RULES:
            hint = did_you_mean(rule, RULES)
            msg = f"{origin}: ignore entry {rule!r} is not a rule id; `citesync rules` lists them{hint}"
            raise CheckError(msg)
    return tuple(value)


# One parser per key; each raises CheckError naming the key.
_PARSE: dict[str, Callable[[object, str], Any]] = {
    "source": lambda value, origin: _path(value, FORMAT_OF, origin, "source"),
    "codemeta-version": _codemeta_version,
    "files": lambda value, origin: _paths(value, CITATION_FILES, origin, "files"),
    "manifests": lambda value, origin: _paths(value, MANIFESTS | DATASET_FILES, origin, "manifests"),
    "write-manifests": _write_manifests,
    "exports": _exports,
    "required-fields": _required_fields,
    "zenodo-contributor-type": _zenodo_contributor_type,
    "keywords-case-sensitive": lambda value, origin: _bool(value, origin, "keywords-case-sensitive"),
    "keywords-ignore-separators": lambda value, origin: _bool(value, origin, "keywords-ignore-separators"),
    "ignore": _ignore,
}


def render(config: Config) -> str:
    """The config as TOML, headed by where it came from (``citesync config``)."""
    lines = [
        f"# from {config.origin}",
        f"source = {json.dumps(config.source)}",
        f"codemeta-version = {json.dumps(config.codemeta_version)}"
        if config.codemeta_version is not None
        else "# codemeta-version: not set, so any supported @context passes",
        f"files = {json.dumps(list(config.files))}"
        if config.files is not None
        else "# files: not set, so every citation file present",
        f"manifests = {json.dumps(list(config.manifests))}"
        if config.manifests is not None
        else "# manifests: not set, so every release manifest at the repo root",
        f"write-manifests = {json.dumps(list(config.write_manifests))}",
        f"exports = {json.dumps(list(config.exports))}",
        "required-fields = {"
        + ", ".join(
            f"{json.dumps(path, ensure_ascii=False)} = {json.dumps(list(terms))}"
            for path, terms in config.required_fields
        )
        + "}",
        f"zenodo-contributor-type = {json.dumps(config.zenodo_contributor_type)}"
        if config.zenodo_contributor_type is not None
        else "# zenodo-contributor-type: not set, so new contributors need a hand edit",
        f"keywords-case-sensitive = {json.dumps(config.keywords_case_sensitive)}",
        f"keywords-ignore-separators = {json.dumps(config.keywords_ignore_separators)}",
        f"ignore = {json.dumps(list(config.ignore))}",
    ]
    return "\n".join(lines)

"""Find and validate the config: the first location found wins, flags override it."""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from citesync.errors import CheckError, UnreadableError
from citesync.formats import CITATION_FILES, CODEMETA_VERSIONS, FORMAT_OF, MANIFESTS, load
from citesync.mapping import TERMS, resolve
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
    keywords_case_sensitive: bool = False
    keywords_ignore_separators: bool = False
    ignore: tuple[str, ...] = ()
    origin: str = "defaults"


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
        if (directory / ".git").exists():
            return directory
    return start


def git_top(start: Path) -> Path | None:
    """The nearest directory from ``start`` up that holds ``.git``: the top of its repo, or None outside one."""
    start = start.resolve()
    return next((directory for directory in (start, *start.parents) if (directory / ".git").exists()), None)


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


def _bool(value: object, origin: str, key: str) -> bool:
    if not isinstance(value, bool):
        msg = f"{origin}: {key} must be true or false"
        raise CheckError(msg)
    return value


def _path(value: object, names: dict[str, str], origin: str, key: str) -> str:
    if not isinstance(value, str) or PurePosixPath(value).name not in names:
        msg = f"{origin}: {key} must name one of {', '.join(names)}, got {value!r}"
        raise CheckError(msg)
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


def did_you_mean(word: str, choices: Iterable[str]) -> str:
    """``; did you mean 'x'?`` for the closest of ``choices``, or nothing when none is close."""
    import difflib  # noqa: PLC0415 - only on an error

    close = difflib.get_close_matches(word, list(choices), n=1)
    return f"; did you mean {close[0]!r}?" if close else ""


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
    "manifests": lambda value, origin: _paths(value, MANIFESTS, origin, "manifests"),
    "write-manifests": _write_manifests,
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
        f"keywords-case-sensitive = {json.dumps(config.keywords_case_sensitive)}",
        f"keywords-ignore-separators = {json.dumps(config.keywords_ignore_separators)}",
        f"ignore = {json.dumps(list(config.ignore))}",
    ]
    return "\n".join(lines)

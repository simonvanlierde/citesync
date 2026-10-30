"""Where a finding's key sits in its file, so editors, annotations and SARIF can point at the line.

Only a check with findings imports this: each file is read again, once, with a parser that keeps positions.
"""

import json
import re
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ruamel.yaml.error import YAMLError

from citesync.formats import Doc, url_label
from citesync.jsonsplice import _node
from citesync.mapping import TERMS, Mapping

if TYPE_CHECKING:
    from citesync.check import Finding

Keys = dict[tuple[str, ...], tuple[int, int]]

_TOML_KEY = re.compile(r"""[A-Za-z0-9_-]+|"(?:[^"\\]|\\.)*"|'[^']*'""")


def place(root: Path, docs: list[Doc], found: Iterable["Finding"], mapping: Mapping) -> set["Finding"]:
    """``found``, each finding on a readable file given the line and column of its term's key.

    A key the file doesn't have points at the nearest table or object above it that it has.
    """
    formats = {d.path: d.format for d in docs if d.readable}
    keys: dict[str, Keys] = {}
    placed = set()
    for f in found:
        if f.file is None or f.term is None or f.line is not None or (fmt := formats.get(f.file)) is None:
            placed.add(f)
            continue
        if f.file not in keys:
            keys[f.file] = key_positions(root / f.file)
        at = _find(keys[f.file], key_paths(fmt, f.term, mapping))
        placed.add(replace(f, line=at[0], column=at[1]) if at else f)
    return placed


def key_paths(fmt: str, term: str, mapping: Mapping) -> list[tuple[str, ...]]:
    """The keys that may hold ``term`` in ``fmt``, by the mapping; a list stops the path, at the list's own key.

    A term the mapping doesn't hold, such as ``@context``, is a top-level key.
    """
    path = mapping[fmt, term] if term in TERMS else term
    if path is None:
        return []
    paths = []
    for alternative in path.split(" | "):
        steps = []
        for step in alternative.split("."):
            steps.append(step.partition("[")[0])
            if "[" in step:
                break
        paths.append(tuple(steps))
    if fmt == "cargo":  # a virtual workspace holds the package fields in [workspace.package]
        paths += [("workspace", *p) for p in paths]
    return paths


def _find(keys: Keys, paths: list[tuple[str, ...]]) -> tuple[int, int] | None:
    for path in paths:  # in the order the reader tries them, a PEP 621 url label as packaging reads it
        labels = (at for key, at in keys.items() if key[:-1] == path[:-1] and url_label(key[-1]) == path[-1])
        if (at := keys.get(path) or next(labels, None)) is not None:
            return at
    for path in paths:  # a key that isn't there: its table or object
        for n in range(len(path) - 1, 0, -1):
            if path[:n] in keys:
                return keys[path[:n]]
    return None


def key_positions(path: Path) -> Keys:
    """(line, column) of every key in the file at ``path`` reached through objects alone, both counted from 1.

    The first of two equal keys wins. An unreadable file has none: positions only help, so they never fail a check.
    """
    try:
        text = path.read_text(encoding="utf-8")
        if path.suffix == ".json":
            return _json_keys(text)
        if path.suffix == ".toml":
            return _toml_keys(text)
        return _yaml_keys(text)
    except (OSError, ValueError, IndexError, YAMLError):
        return {}


def _json_keys(text: str) -> Keys:
    keys: Keys = {}

    def walk(node: tuple[int, int, Any, Any], parent: tuple[str, ...]) -> None:
        for key, child in (node[2] or {}).items():
            if child[3] is None:  # a list's elements
                return
            keys.setdefault((*parent, key), _line_column(text, child[3]))
            walk(child, (*parent, key))

    walk(_node(text, 0), ())
    return keys


def _line_column(text: str, offset: int) -> tuple[int, int]:
    return text.count("\n", 0, offset) + 1, offset - text.rfind("\n", 0, offset)


def _yaml_keys(text: str) -> Keys:
    from ruamel.yaml import YAML  # noqa: PLC0415 - the round-trip loader, which records where each key sits

    keys: Keys = {}
    seen: set[int] = set()  # an alias can repeat a mapping, or hold itself

    def walk(node: Any, parent: tuple[str, ...]) -> None:  # noqa: ANN401 - a round-trip YAML node
        if not isinstance(node, dict) or id(node) in seen or not hasattr(node, "lc"):
            return
        seen.add(id(node))
        for key, (line, column, *_) in node.lc.data.items():
            keys.setdefault((*parent, str(key)), (line + 1, column + 1))
            walk(node.get(key), (*parent, str(key)))

    walk(YAML().load(text), ())
    return keys


def _toml_keys(text: str) -> Keys:
    """A line scan of the keys and table headers: tomllib keeps no positions, and tomlkit costs 10 ms to import.

    shortcut: a key inside a multi-line array of inline tables isn't seen, and an array's last ``["a"]`` with no
    comma reads as a header; findings stop at the array's key anyway.
    """
    keys: Keys = {}
    table: tuple[str, ...] = ()
    closing = None  # the quotes that end the multi-line string the scan is in
    for n, line in enumerate(text.splitlines(), 1):
        if closing:
            closing = None if closing in line else closing
            continue
        body = line.lstrip(" \t")
        if body.startswith("["):
            bracket = "]]" if body.startswith("[[") else "]"
            found = _dotted_key(line, len(line) - len(body) + len(bracket))
            rest = line[found[1] + len(bracket) :].lstrip(" \t") if found else ""
            if found and line.startswith(bracket, found[1]) and rest[:1] in {"", "#"}:  # not `["a"],` in an array
                table = tuple(name for name, _ in found[0])
                _record(keys, (), found[0], n)
            continue
        found = _dotted_key(line, 0)
        if found and line.startswith("=", found[1]):
            _record(keys, table, found[0], n)
            value = line[found[1] + 1 :].lstrip()
            closing = next((q for q in ('"""', "'''") if value.startswith(q) and value.count(q) == 1), None)
    return keys


def _dotted_key(line: str, i: int) -> tuple[list[tuple[str, int]], int] | None:
    """The parts of the dotted key at ``i`` in ``line``, each with its column, and where the key ends."""
    parts = []
    while True:
        i = len(line) - len(line[i:].lstrip(" \t"))
        match = _TOML_KEY.match(line, i)
        if not match:
            return None
        token = match[0]
        name = json.loads(token) if token[0] == '"' else token.strip("'") if token[0] == "'" else token
        parts.append((name, i + 1))
        i = len(line) - len(line[match.end() :].lstrip(" \t"))
        if not line.startswith(".", i):
            return parts, i
        i += 1


def _record(keys: Keys, table: tuple[str, ...], parts: list[tuple[str, int]], line: int) -> None:
    for n in range(1, len(parts) + 1):
        keys.setdefault((*table, *(name for name, _ in parts[:n])), (line, parts[n - 1][1]))

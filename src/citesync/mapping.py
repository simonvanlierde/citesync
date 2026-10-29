"""The vendored field mapping, and the path grammar its rows use.

The mapping says where each CodeMeta term sits in each format. Its contract is
docs/mapping-export.md in codemeta-drift, and MAPPING_SOURCE names the commit
it was copied from.
"""

import json
import re
from functools import cache
from importlib.resources import files
from typing import Any

from citesync.errors import CheckError

SCHEMA_MAJOR = "1"
FORMATS = ("cff-1.2.0", "codemeta", "zenodo", "pep621", "cargo", "npm")
TERMS = ("name", "version", "author", "license", "identifier", "codeRepository", "description", "keywords")
PERSON_TERMS = ("author.givenName", "author.familyName", "author.@id")

_STEP = re.compile(r"^(@?[A-Za-z_][A-Za-z0-9_-]*)(?:\[\]|\[(@?[A-Za-z_][A-Za-z0-9_-]*)=([A-Za-z0-9_.-]+)\])?$")

type Mapping = dict[tuple[str, str], str | None]
"""(format, term) to path, or None when the format has no place for the term."""


@cache
def load_mapping(name: str = "mapping-local.json") -> Mapping:
    """Read the vendored mapping and check what citesync needs from it.

    Raises:
        CheckError: on an unknown schema major, a duplicate row, or a missing row
            for a term citesync reads.
    """
    data = json.loads(files("citesync").joinpath(name).read_text(encoding="utf-8"))
    return check_mapping(data, name)


def check_mapping(data: dict[str, Any], name: str) -> Mapping:
    """Turn a parsed mapping export into a lookup table, refusing what citesync can't use."""
    major = str(data.get("schema_version", "")).split(".")[0]
    if major != SCHEMA_MAJOR:
        msg = f"{name}: schema_version {data.get('schema_version')!r}, this build reads {SCHEMA_MAJOR}.x"
        raise CheckError(msg)
    rows: Mapping = {}
    for row in data["rows"]:
        key = (row["format"], row["term"])
        if key in rows:
            msg = f"{name}: two rows for {key[0]} {key[1]}"
            raise CheckError(msg)
        rows[key] = row["path"]
    missing = [f"{fmt} {term}" for fmt in FORMATS for term in TERMS + PERSON_TERMS if (fmt, term) not in rows]
    if missing:
        msg = f"{name}: no row for {', '.join(missing)}"
        raise CheckError(msg)
    for (fmt, term), path in rows.items():
        if path is not None and fmt in FORMATS:
            _parse(path)  # fail on load, not on the first file that uses the row
        if term in PERSON_TERMS and path is not None and rows.get((fmt, "author")) is None:
            msg = f"{name}: {fmt} {term} has a path but {fmt} author has none"
            raise CheckError(msg)
    return rows


def _parse(path: str) -> list[list[tuple[str, str | None, str | None, bool]]]:
    """Split a path into alternatives of steps: (key, filter key, filter value, is a list step)."""
    alternatives = []
    for alternative in path.split(" | "):
        steps = []
        for step in alternative.split("."):
            match = _STEP.match(step)
            if not match:
                msg = f"mapping path {path!r}: bad step {step!r}"
                raise CheckError(msg)
            steps.append((match[1], match[2], match[3], step.endswith("]")))
        alternatives.append(steps)
    return alternatives


def resolve(doc: Any, path: str) -> list[Any]:  # noqa: ANN401 - parsed JSON, TOML or YAML
    """Every value at ``path`` in ``doc``, from the first alternative that has any.

    A plain step reads a key of a mapping; ``key[]`` reads each element of a list;
    ``key[k=v]`` reads the elements whose ``k`` equals ``v``. An empty list means the
    path does not exist in ``doc``.
    """
    for steps in _parse(path):
        nodes = [doc]
        for key, fkey, fvalue, is_list in steps:
            found = [node[key] for node in nodes if isinstance(node, dict) and key in node]
            if is_list:
                elements = [el for value in found if isinstance(value, list) for el in value]
                if fkey is not None:
                    elements = [el for el in elements if isinstance(el, dict) and str(el.get(fkey)) == fvalue]
                found = elements
            nodes = found
        if nodes:
            return nodes
    return []


def relative(path: str, parent: str) -> str:
    """A person sub-term path relative to its term's path: ``authors[].orcid`` under ``authors[]`` is ``orcid``.

    Each alternative of ``path`` must start with ``parent``. The result is ``""``
    when the sub-term is the element itself (Cargo's one ``Name <email>`` string).
    """
    parts = []
    for alternative in path.split(" | "):
        if alternative == parent:
            parts.append("")
        elif alternative.startswith(parent + "."):
            parts.append(alternative.removeprefix(parent + "."))
        else:
            msg = f"mapping path {path!r} does not start with its term's path {parent!r}"
            raise CheckError(msg)
    return " | ".join(parts)

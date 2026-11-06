"""The vendored field mapping, and the path grammar its rows use.

The mapping says where each CodeMeta term sits in each format. Its contract is
docs/mapping-export.md in codemeta-drift, and MAPPING_SOURCE names the
codemeta-drift release and commit it was copied from.
"""

import json
import re
from functools import cache
from pathlib import Path
from typing import Any

from citesync.errors import CheckError

SCHEMA_MAJOR = "1"
FORMATS = ("cff-1.2.0", "codemeta", "zenodo", "pep621", "cargo", "npm")
"""The formats citesync reads and writes."""
IMPORTED = ("pkg-info", "r-description", "julia")
"""The formats citesync only reads, as a source."""
TERMS = (
    "name",
    "version",
    "author",
    "contributor",
    "license",
    "identifier",
    "swhid",
    "codeRepository",
    "description",
    "keywords",
    "datePublished",
)
EXPORT_TERMS = ("publisher",)
"""Terms read into the record for the exports only: check and write leave them alone."""
PEOPLE = ("author", "contributor")
"""The terms that hold a list of people."""


def person_terms(term: str) -> tuple[str, str, str]:
    """The given name, family name and ORCID sub-terms of ``term``, one of :data:`PEOPLE`."""
    return f"{term}.givenName", f"{term}.familyName", f"{term}.@id"


PERSON_TERMS = tuple(sub for term in PEOPLE for sub in person_terms(term))

_KEY = r"@?[A-Za-z_][A-Za-z0-9_@-]*(?::[A-Za-z_][A-Za-z0-9_-]*)?"  # a prefixed key such as dcterms:creator
_STEP = re.compile(rf"^({_KEY})(?:\[\]|\[({_KEY})=([A-Za-z0-9_.-]+)\])?$")

type Mapping = dict[tuple[str, str], str | None]
"""(format, term) to path, or None when the format has no place for the term."""


@cache
def load_mapping() -> Mapping:
    """Read the vendored mapping and check what citesync needs from it.

    Raises:
        CheckError: on an unknown schema major, a duplicate row, or a missing row
            for a term citesync reads.
    """
    name = "mapping-local.json"
    # NOTE: read beside this module, not through importlib.resources, whose imports cost 5 ms a run.
    # That needs an install on disk; switch back if citesync ever runs from a zip.
    data = json.loads(Path(__file__).with_name(name).read_text(encoding="utf-8"))
    return check_mapping(data, name)


def check_mapping(data: dict[str, Any], name: str) -> Mapping:  # noqa: C901 - one check per way a row is unusable
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
    missing = [
        f"{fmt} {term}" for fmt in FORMATS + IMPORTED for term in TERMS + PERSON_TERMS if (fmt, term) not in rows
    ]
    if missing:
        msg = f"{name}: no row for {', '.join(missing)}"
        raise CheckError(msg)
    for (fmt, term), path in rows.items():
        if path is not None:
            _parse(path)  # fail on load, not on the first file that uses the row
            if " + " in path and fmt in FORMATS:  # write and positions place one value per alternative
                msg = f"{name}: {fmt} {term} reads parts with +, which citesync can't write back"
                raise CheckError(msg)
        parent = term.partition(".")[0]
        if term in PERSON_TERMS and path is not None:
            if (parent_path := rows.get((fmt, parent))) is None:
                msg = f"{name}: {fmt} {term} has a path but {fmt} {parent} has none"
                raise CheckError(msg)
            try:
                relative(path, parent_path)
            except CheckError as err:
                msg = f"{name}: {fmt} {term}: {err}"
                raise CheckError(msg) from err
    return rows


type _Step = tuple[str, str | None, str | None, bool]


def _parse(path: str) -> list[list[list[_Step]]]:
    """Split a path into alternatives, each a list of ``+`` parts, each a list of steps.

    A step is (key, filter key, filter value, is a list step).
    """
    alternatives = []
    for alternative in path.split(" | "):
        parts = []
        for part in alternative.split(" + "):
            steps = []
            for step in re.split(r"\.(?![^\[\]]*\])", part):  # a dot inside [k=v] is part of the value
                match = _STEP.match(step)
                if not match:
                    msg = f"mapping path {path!r}: bad step {step!r}"
                    raise CheckError(msg)
                steps.append((match[1], match[2], match[3], step.endswith("]")))
            parts.append(steps)
        alternatives.append(parts)
    return alternatives


def resolve(doc: Any, path: str) -> list[Any]:  # noqa: ANN401 - parsed JSON, TOML or YAML
    """Every value at ``path`` in ``doc``, from the first alternative that has any.

    A plain step reads a key of a mapping; ``key[]`` reads each element of a list;
    ``key[k=v]`` reads the elements whose ``k`` is ``v`` or is a list that holds ``v``.
    ``a + b`` reads both parts, ``a``'s values first, and binds tighter than ``|``.
    An empty list means the path does not exist in ``doc``.
    """
    for parts in _parse(path):
        if nodes := [node for steps in parts for node in _chain(doc, steps)]:
            return nodes
    return []


def _chain(doc: Any, steps: list[_Step]) -> list[Any]:  # noqa: ANN401 - parsed JSON, TOML or YAML
    nodes = [doc]
    for key, fkey, fvalue, is_list in steps:
        nodes = [node[key] for node in nodes if isinstance(node, dict) and key in node]
        if is_list:
            nodes = [el for value in nodes if isinstance(value, list) for el in value]
            if fkey is not None:
                nodes = [el for el in nodes if isinstance(el, dict) and fvalue in _texts(el.get(fkey))]
    return nodes


def _texts(value: Any) -> list[str]:  # noqa: ANN401 - parsed JSON, TOML or YAML
    """A filter's value as text: each member of a list (R's role vectors), else the value itself."""
    if value is None:
        return []
    return [str(v) for v in value] if isinstance(value, list) else [str(value)]


def relative(path: str, parent: str, alternative: int = 0) -> str:
    """A person sub-term path relative to its term's path: ``authors[].orcid`` under ``authors[]`` is ``orcid``.

    The sub-term's alternatives pair with the term's by position, and this reads the one at
    ``alternative``, the alternative the term resolved through, so one person's ORCID never
    comes from another list. The result is ``""`` when the sub-term is the element itself
    (Cargo's one ``Name <email>`` string, or each part of pkg-info's ``Author + Author-email``).

    Raises:
        CheckError: when the alternatives don't pair up, each starting with its term's.
    """
    subs, parents = path.split(" | "), parent.split(" | ")
    paired = len(subs) == len(parents)
    if not paired or any(s != p and not s.startswith(p + ".") for s, p in zip(subs, parents, strict=True)):
        msg = f"mapping path {path!r} does not follow its term's path {parent!r}, alternative by alternative"
        raise CheckError(msg)
    return subs[alternative].removeprefix(parents[alternative]).removeprefix(".")

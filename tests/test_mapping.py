"""The vendored mapping: provenance, schema, the runtime checks, and the path grammar."""

import copy
import hashlib
import json
from collections.abc import Callable
from importlib.resources import files

import jsonschema
import pytest

from citesync.errors import CheckError
from citesync.formats import FORMAT_OF
from citesync.mapping import FORMATS, IMPORTED, check_mapping, load_mapping, relative, resolve

PACKAGE = files("citesync")


def _json(name: str) -> dict:
    return json.loads(PACKAGE.joinpath(name).read_text(encoding="utf-8"))


def test_vendored_files_match_mapping_source() -> None:
    lines = PACKAGE.joinpath("MAPPING_SOURCE").read_text(encoding="utf-8").splitlines()
    pinned = {line.split()[2]: line.split()[1] for line in lines if line.startswith("sha256 ")}
    assert set(pinned) == {"mapping-local.json", "mapping-4.0.json", "mapping.schema.json", "mapping-vectors.json"}
    for name, digest in pinned.items():
        assert hashlib.sha256(PACKAGE.joinpath(name).read_bytes()).hexdigest() == digest, (
            f"{name} differs from MAPPING_SOURCE: after vendoring a new codemeta-drift tag, set the tag, commit and"
            f" the line's hash from `sha256sum src/citesync/{name}`"
        )


@pytest.mark.parametrize("name", ["mapping-local.json", "mapping-4.0.json"])
def test_mapping_validates_against_vendored_schema(name: str) -> None:
    jsonschema.validate(_json(name), _json("mapping.schema.json"))


def test_loads() -> None:
    mapping = load_mapping()
    assert mapping["cff-1.2.0", "identifier"] == "doi | identifiers[type=doi].value"
    assert mapping["cargo", "identifier"] is None
    assert mapping["codemeta", "swhid"] == mapping["codemeta", "identifier"] == "identifier"


def test_formats_are_in_file_order() -> None:
    """Files other than the source are checked in FORMATS order, so blame never depends on config order."""
    assert tuple(dict.fromkeys(FORMAT_OF.values())) == FORMATS + IMPORTED


def _row(data: dict, fmt: str, term: str) -> dict:
    return next(r for r in data["rows"] if (r["format"], r["term"]) == (fmt, term))


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.update(schema_version="2.0"), "schema_version '2.0'"),
        (lambda d: d["rows"].pop(0), "no row for cff-1.2.0 name"),
        (lambda d: d["rows"].append(dict(d["rows"][0])), "two rows for cff-1.2.0 name"),
        (lambda d: d["rows"][0].update(path="title[0]"), "bad step 'title[0]'"),
        (lambda d: _row(d, "doap", "name").update(path="doap:name[0]"), "bad step 'doap:name[0]'"),
        (lambda d: _row(d, "julia", "author.@id").update(path="orcid"), "julia author.@id: mapping path 'orcid'"),
        (lambda d: d["rows"].remove(_row(d, "pkg-info", "name")), "no row for pkg-info name"),
        (lambda d: d["rows"].remove(_row(d, "cff-1.2.0", "author.@id")), "no row for cff-1.2.0 author.@id"),
        (
            lambda d: _row(d, "pep621", "author").update(path=None),
            "pep621 author.givenName has a path but pep621 author has none",
        ),
    ],
)
def test_mapping_refused(change: Callable[[dict], object], message: str) -> None:
    data = copy.deepcopy(_json("mapping-local.json"))
    change(data)
    with pytest.raises(CheckError, match=message.replace("[", r"\[")):
        check_mapping(data, "mapping-local.json")


DOC = {
    "a": {"b": "plain"},
    "list": [{"type": "url", "v": 1}, {"type": "doi", "v": 2}, {"type": "doi", "v": 3}, "loose"],
    "@id": "at",
    "empty": [],
}


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("a.b", ["plain"]),
        ("a", [{"b": "plain"}]),
        ("a.missing", []),
        ("list[]", DOC["list"]),
        ("list[].v", [1, 2, 3]),
        ("list[type=doi].v", [2, 3]),
        ("list[type=isbn].v", []),
        ("@id", ["at"]),
        ("missing | a.b", ["plain"]),
        ("a.b | @id", ["plain"]),
        ("empty[] | list[type=url].v", [1]),
        ("a.b.c", []),
    ],
)
def test_resolve(path: str, expected: list) -> None:
    assert resolve(DOC, path) == expected


def test_relative() -> None:
    assert relative("authors[].given-names", "authors[]") == "given-names"
    assert relative("package.authors[]", "package.authors[]") == ""
    with pytest.raises(CheckError):
        relative("other.name", "authors[]")
    assert relative("Author + Author-email", "Author + Author-email") == ""


def test_relative_pairs_alternatives_by_position() -> None:
    """A sub-term reads from the alternative its term resolved through, so an ORCID stays with its person."""
    path, parent = "doap:developer[].@id | doap:maintainer[].@id", "doap:developer[] | doap:maintainer[]"
    assert relative(path, parent) == "@id"
    assert relative("a[].given | b[].name", "a[] | b[]", 1) == "name"
    with pytest.raises(CheckError):
        relative("a[].x", "a[] | b[]")
    with pytest.raises(CheckError):
        relative("b[].x | a[].x", "a[] | b[]")


VECTORS = _json("mapping-vectors.json")["cases"]


@pytest.mark.parametrize("case", VECTORS, ids=lambda c: c["name"])
def test_resolve_vector(case: dict) -> None:
    assert resolve(case["document"], case["path"]) == case["expected"]


def test_a_plus_path_in_a_written_format_is_refused() -> None:
    data = _json("mapping-local.json")
    for row in data["rows"]:
        if (row["format"], row["term"]) == ("npm", "author"):
            row["path"] = "author + contributors[]"
    with pytest.raises(CheckError, match="npm author reads parts with \\+"):
        check_mapping(data, "mapping-local.json")

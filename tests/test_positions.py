"""Where a finding's key sits in each format, found only once a finding needs it."""

from pathlib import Path

import pytest

from citesync.check import Finding
from citesync.formats import Doc
from citesync.mapping import load_mapping
from citesync.positions import key_positions, place

TOML = """\
# version = "0.0.0" in a comment
[build-system]
requires = []

[project]
name = "x"
description = '''
version = "not a key"
'''
"version" = "1.0"
keywords = [
  "alpha",
]

[project.urls]
"Source Code" = "https://example.org/x"

[[project.authors]]
name = "Marie Curie"
"""

YAML = """\
cff-version: 1.2.0
title: x
authors:
  - given-names: Tu
    family-names: Youyou
identifiers:
  - type: doi
    value: 10.5555/12345
"""

JSON = '{\n  "name": "x",\n  "author": [{"name": "Ada Lovelace"}],\n  "nested": {"key\\"q": 1}\n}\n'


@pytest.mark.parametrize(
    ("name", "text", "key", "at"),
    [
        ("pyproject.toml", TOML, ("project", "version"), (10, 1)),
        ("pyproject.toml", TOML, ("project", "name"), (6, 1)),
        ("pyproject.toml", TOML, ("project", "keywords"), (11, 1)),
        ("pyproject.toml", TOML, ("project", "urls"), (15, 10)),
        ("pyproject.toml", TOML, ("project", "urls", "Source Code"), (16, 1)),
        ("pyproject.toml", TOML, ("project", "authors"), (18, 11)),
        ("CITATION.cff", YAML, ("title",), (2, 1)),
        ("CITATION.cff", YAML, ("identifiers",), (6, 1)),
        ("codemeta.json", JSON, ("name",), (2, 3)),
        ("codemeta.json", JSON, ("author",), (3, 3)),
        ("codemeta.json", JSON, ("nested", 'key"q'), (4, 14)),
    ],
)
def test_key_positions(name: str, text: str, key: tuple[str, ...], at: tuple[int, int], tmp_path: Path) -> None:
    (tmp_path / name).write_text(text, encoding="utf-8")
    assert key_positions(tmp_path / name)[key] == at


def test_toml_keys_inside_a_multiline_string_or_a_comment_are_not_keys(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(TOML, encoding="utf-8")
    keys = key_positions(tmp_path / "pyproject.toml")
    assert keys[("project", "version")] == (10, 1)
    assert ("version",) not in keys


def test_cargo_dotted_and_workspace_keys(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text(
        '[workspace.package]\nlicense = "MIT"\n\n[package]\nname = "x"\nversion.workspace = true\n', "utf-8"
    )
    keys = key_positions(tmp_path / "Cargo.toml")
    assert keys[("package", "version")] == (6, 1)
    assert keys[("workspace", "package", "license")] == (2, 1)


def test_place_points_at_the_term_and_falls_back_to_its_table(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(TOML, encoding="utf-8")
    doc = Doc("pyproject.toml", "pep621", {}, frozenset(), None, release=True)
    found = {
        Finding("pyproject.toml", "version", "version-mismatch", "m"),
        Finding("pyproject.toml", "codeRepository", "repository-mismatch", "m"),  # `Source Code` reads as Source
        Finding("pyproject.toml", "license", "license-mismatch", "m"),  # no such key
        Finding(None, "contributor", "not-checked", "m"),
    }
    placed = {f.rule: (f.line, f.column) for f in place(tmp_path, [doc], found, load_mapping())}
    assert placed == {
        "version-mismatch": (10, 1),
        "repository-mismatch": (16, 1),
        "license-mismatch": (5, 2),
        "not-checked": (None, None),
    }


def test_an_unparsable_file_gets_no_positions(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text("title: [x\n", encoding="utf-8")
    assert key_positions(tmp_path / "CITATION.cff") == {}

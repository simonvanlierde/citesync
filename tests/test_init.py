"""`citesync init`: a CITATION.cff from the files a repo already has."""

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from ruamel.yaml import YAML

if TYPE_CHECKING:
    from tests.conftest import Run

SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic-agree"
PYPROJECT = """\
[build-system]
requires = ["uv_build>=0.8,<0.9"]
build-backend = "uv_build"

[project]
name = "radium"
version = "0.4.0"
description = "Measures what glows."
authors = [{ name = "Marie Curie" }, { name = "Tu Youyou" }]
license = "MIT"
keywords = ["chemistry", "physics"]

[project.urls]
Source = "https://example.org/radium"
"""


def _cff(root: Path) -> dict:
    """The CITATION.cff, checked for the keys CFF 1.2.0 requires."""
    data = YAML(typ="safe").load((root / "CITATION.cff").read_text(encoding="utf-8"))
    assert {"cff-version", "message", "title", "authors"} <= data.keys()
    assert data["cff-version"] == "1.2.0"
    assert data["authors"]
    assert all("family-names" in a or "name" in a for a in data["authors"])
    return data


def test_init_from_every_file_passes_check(tmp_path: Path, run: "Run") -> None:
    root = tmp_path / "repo"
    shutil.copytree(SYNTHETIC, root)
    (root / "CITATION.cff").unlink()
    assert run("init", "--root", str(root)) == (0, "wrote CITATION.cff\n", "")
    data = _cff(root)
    assert data["title"] == "synthagree"
    assert data["doi"] == "10.5281/zenodo.1234567"
    assert data["authors"][0] == {
        "given-names": "Ada",
        "family-names": "Lovelace",
        "orcid": "https://orcid.org/0000-0002-1825-0097",
    }
    code, out, _ = run("check", "--root", str(root))
    assert code == 0, out


def test_init_says_to_check_a_split_name(tmp_path: Path, run: "Run") -> None:
    pyproject = PYPROJECT.replace('{ name = "Tu Youyou" }', '{ name = "Antonie van Leeuwenhoek" }')
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    code, out, _ = run("init", "--root", str(tmp_path))
    assert code == 0
    assert out.splitlines()[1:] == [
        "check the name split: 'Marie Curie' became given 'Marie', family 'Curie'",
        "check the name split: 'Antonie van Leeuwenhoek' became given 'Antonie van', family 'Leeuwenhoek'",
    ]


def test_init_from_pyproject_alone_passes_check(tmp_path: Path, run: "Run") -> None:
    root = tmp_path
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    assert run("init", "--root", str(root))[0] == 0
    data = _cff(root)
    assert data["title"] == "radium"
    assert data["abstract"] == "Measures what glows."
    assert data["version"] == "0.4.0"
    assert data["license"] == "MIT"
    assert data["repository-code"] == "https://example.org/radium"
    assert data["keywords"] == ["chemistry", "physics"]
    assert data["authors"] == [
        {"given-names": "Marie", "family-names": "Curie"},
        {"given-names": "Tu", "family-names": "Youyou"},
    ]
    code, out, _ = run("check", "--root", str(root))
    assert code == 0, out


def test_init_refuses_an_existing_citation_file(tmp_path: Path, run: "Run") -> None:
    root = tmp_path / "repo"
    shutil.copytree(SYNTHETIC, root)
    before = (root / "CITATION.cff").read_bytes()
    code, out, err = run("init", "--root", str(root))
    assert (code, out) == (2, "")
    assert "CITATION.cff already exists" in err
    assert (root / "CITATION.cff").read_bytes() == before


def test_init_diff_writes_nothing(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    code, out, _ = run("init", "--diff", "--root", str(tmp_path))
    assert code == 0
    assert out.startswith("--- /dev/null\n+++ b/CITATION.cff\n")
    assert "+title: radium\n" in out
    assert not (tmp_path / "CITATION.cff").exists()


@pytest.mark.parametrize(
    ("pyproject", "message"),
    [
        (None, "no codemeta.json, .zenodo.json or package manifest"),
        ('[project]\nname = "radium"\n', "no authors"),
        ('[project]\nauthors = [{ name = "Tu Youyou" }]\n', "no title"),
    ],
)
def test_init_refuses_without_a_title_or_authors(
    pyproject: str | None, message: str, tmp_path: Path, run: "Run"
) -> None:
    if pyproject:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    code, _, err = run("init", "--root", str(tmp_path))
    assert code == 2
    assert message in err
    assert not (tmp_path / "CITATION.cff").exists()


def test_init_names_a_field_it_left_out(tmp_path: Path, run: "Run") -> None:
    pyproject = PYPROJECT.replace('"MIT"', '"MIT AND Apache-2.0"')
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    code, out, _ = run("init", "--root", str(tmp_path))
    assert (code, out.splitlines()[0]) == (
        0,
        "wrote CITATION.cff, leaving out license: a licence list can only say OR, not AND or WITH",
    )
    assert "license" not in _cff(tmp_path)


LONG = "Measures what glows, and how long it keeps glowing, in a description longer than a YAML line wraps at."
WRITTEN = f"""\
cff-version: 1.2.0
message: If you use this software, please cite it as below.
type: software
title: radium
abstract: {LONG}
version: 0.4.0
authors:
  - given-names: Marie
    family-names: Curie
  - given-names: Tu
    family-names: Youyou
repository-code: https://example.org/radium
license: MIT
keywords:
  - chemistry
  - physics
"""


def test_init_writes_this_text(tmp_path: Path, run: "Run") -> None:
    """The keys in CFF's order, sequences indented under their key, and no line wrapped."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT.replace("Measures what glows.", LONG), encoding="utf-8")
    assert run("init", "--root", str(tmp_path))[0] == 0
    assert (tmp_path / "CITATION.cff").read_text(encoding="utf-8") == WRITTEN


def test_init_takes_each_field_from_the_first_file_that_has_it(tmp_path: Path, run: "Run") -> None:
    codemeta = {
        "@context": "https://w3id.org/codemeta/3.0",
        "name": "radium",
        "datePublished": "1898-12-26",
        "author": [{"@type": "Person", "givenName": "Marie", "familyName": "Curie"}],
    }
    (tmp_path / "codemeta.json").write_text(json.dumps(codemeta), encoding="utf-8")
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    assert run("init", "--root", str(tmp_path))[0] == 0
    text = (tmp_path / "CITATION.cff").read_text(encoding="utf-8")
    assert "title: radium\nabstract: Measures what glows.\nversion: 0.4.0\ndate-released: 1898-12-26\n" in text
    assert "authors:\n  - given-names: Marie\n    family-names: Curie\nrepository-code:" in text


def test_init_refuses_a_dangling_citation_file_link(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "CITATION.cff").symlink_to(tmp_path / "elsewhere.cff")
    code, _, err = run("init", "--root", str(tmp_path))
    assert (code, err) == (
        2,
        "citesync: CITATION.cff already exists; `citesync write` makes it agree with another file\n",
    )
    assert not (tmp_path / "elsewhere.cff").exists()


def test_init_refuses_when_a_file_cannot_be_read(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text("{", encoding="utf-8")
    code, _, err = run("init", "--root", str(tmp_path))
    assert code == 2
    assert err.startswith("citesync: codemeta.json:1:2: ")
    assert not (tmp_path / "CITATION.cff").exists()


def test_init_names_every_file_it_read_for_a_missing_title(tmp_path: Path, run: "Run") -> None:
    pyproject = '[build-system]\nbuild-backend = "uv_build"\n\n[project]\nauthors = [{ name = "Tu Youyou" }]\n'
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (tmp_path / "package.json").write_text('{"author": "Tu Youyou"}\n', encoding="utf-8")
    code, _, err = run("init", "--root", str(tmp_path))
    assert (code, err) == (2, "citesync: no title in pyproject.toml, package.json, and CITATION.cff needs one\n")


CARGO = """\
[package]
name = "radium"
version = "0.4.0"
description = "Measures what glows."
authors = ["Marie Curie <marie@example.org>"]
license = "MIT OR Apache-2.0"
repository = "https://example.org/radium"
keywords = ["chemistry"]
"""
PACKAGE = {
    "name": "radium",
    "version": "0.4.0",
    "description": "Measures what glows.",
    "author": "Marie Curie <marie@example.org> (https://example.org)",
    "license": "MIT",
    "keywords": ["chemistry"],
}


@pytest.mark.parametrize(
    ("files", "left"),
    [
        (
            {
                "pyproject.toml": PYPROJECT.replace('["chemistry", "physics"]', '["lca"]'),
                "package.json": json.dumps({**PACKAGE, "keywords": ["cli"]}),
            },
            "",
        ),
        (
            {"Cargo.toml": CARGO},
            ", leaving out license: a list: with no .zenodo.json, Zenodo reads one licence and refuses the release",
        ),
        (
            {
                "Cargo.toml": CARGO,
                ".zenodo.json": json.dumps({"title": "radium", "creators": [{"name": "Curie, Marie"}]}),
            },
            "",
        ),
        ({"package.json": json.dumps(PACKAGE)}, ""),
    ],
    ids=["keywords-from-two-manifests", "cargo-dual-licence", "dual-licence-with-zenodo", "package-json"],
)
def test_init_then_check_passes(files: dict[str, str], left: str, tmp_path: Path, run: "Run") -> None:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    code, out, _ = run("init", "--root", str(tmp_path))
    assert (code, out.startswith(f"wrote CITATION.cff{left}\n")) == (0, True), out
    code, out, _ = run("check", "--root", str(tmp_path))
    assert code == 0, out

"""`citesync init`: a CITATION.cff from the files a repo already has."""

import shutil
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from citesync.cli import main

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


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def _cff(root: Path) -> dict:
    """The CITATION.cff, checked for the keys CFF 1.2.0 requires."""
    data = YAML(typ="safe").load((root / "CITATION.cff").read_text(encoding="utf-8"))
    assert {"cff-version", "message", "title", "authors"} <= data.keys()
    assert data["cff-version"] == "1.2.0"
    assert data["authors"]
    assert all("family-names" in a or "name" in a for a in data["authors"])
    return data


def test_init_from_every_file_passes_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "repo"
    shutil.copytree(SYNTHETIC, root)
    (root / "CITATION.cff").unlink()
    assert _run(capsys, "init", "--root", str(root)) == (0, "wrote CITATION.cff\n", "")
    data = _cff(root)
    assert data["title"] == "synthagree"
    assert data["doi"] == "10.5281/zenodo.1234567"
    assert data["authors"][0] == {
        "given-names": "Ada",
        "family-names": "Lovelace",
        "orcid": "https://orcid.org/0000-0002-1825-0097",
    }
    code, out, _ = _run(capsys, "check", "--root", str(root))
    assert code == 0, out


def test_init_from_pyproject_alone_passes_check(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    assert _run(capsys, "init", "--root", str(root))[0] == 0
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
    code, out, _ = _run(capsys, "check", "--root", str(root))
    assert code == 0, out


def test_init_refuses_an_existing_citation_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "repo"
    shutil.copytree(SYNTHETIC, root)
    before = (root / "CITATION.cff").read_bytes()
    code, out, err = _run(capsys, "init", "--root", str(root))
    assert (code, out) == (2, "")
    assert "CITATION.cff already exists" in err
    assert (root / "CITATION.cff").read_bytes() == before


def test_init_diff_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    code, out, _ = _run(capsys, "init", "--diff", "--root", str(tmp_path))
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
    pyproject: str | None, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if pyproject:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    code, _, err = _run(capsys, "init", "--root", str(tmp_path))
    assert code == 2
    assert message in err
    assert not (tmp_path / "CITATION.cff").exists()


def test_init_names_a_field_it_left_out(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pyproject = PYPROJECT.replace('"MIT"', '"MIT AND Apache-2.0"')
    (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    code, out, _ = _run(capsys, "init", "--root", str(tmp_path))
    assert (code, out) == (
        0,
        "wrote CITATION.cff, leaving out license: a licence list can only say OR, not AND or WITH\n",
    )
    assert "license" not in _cff(tmp_path)

"""Typst and Quarto plugin manifests: checked and written like the package manifests whose fields they share."""

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.conftest import Run

SYNTHETIC = Path(__file__).parent / "fixtures" / "synthetic-agree"
# The shapes credit-matrix ships in integrations/typst and integrations/quarto, with synthagree's metadata.
TYPST = """\
[package]
name = "synthagree"
version = "{version}"
entrypoint = "lib.typ"
authors = ["Ada Lovelace", "Alan Turing"]
license = "Apache-2.0"
description = "A made-up package."
repository = "https://github.com/example/synthagree"
keywords = ["alpha", "beta"]
categories = ["model"]
compiler = "0.14.0"
"""
QUARTO = """\
# Quarto reads this file; citesync keeps version and author in step.
title: synthagree filter
author: Ada Lovelace
version: {version}
quarto-required: ">=1.4.0"
contributes:
  filters:
    - synthagree.lua
"""
TYPST_PATH = "integrations/typst/typst.toml"
QUARTO_PATH = "integrations/quarto/_extensions/synthagree/_extension.yml"


def _repo(tmp_path: Path, version: str, write_manifests: str = '["version"]') -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    shutil.copy(SYNTHETIC / "CITATION.cff", root / "CITATION.cff")
    for path, text in ((TYPST_PATH, TYPST), (QUARTO_PATH, QUARTO)):
        (root / path).parent.mkdir(parents=True)
        (root / path).write_text(text.format(version=version), encoding="utf-8")
    config = f'manifests = ["{TYPST_PATH}", "{QUARTO_PATH}"]\nwrite-manifests = {write_manifests}\n'
    (root / "citesync.toml").write_text(config, encoding="utf-8")
    return root


def test_plugin_manifests_that_agree_pass(tmp_path: Path, run: "Run") -> None:
    code, out, _ = run("check", "--root", str(_repo(tmp_path, "1.2.3")))
    assert code == 0, out


def test_check_reports_a_stale_plugin_version(tmp_path: Path, run: "Run") -> None:
    code, out, _ = run("check", "--root", str(_repo(tmp_path, "0.1.0")))
    assert code == 1
    assert f"{TYPST_PATH}:3:1: error[version-mismatch] version: '0.1.0', CITATION.cff has '1.2.3'" in out
    assert f"{QUARTO_PATH}:4:1: error[version-mismatch] version: '0.1.0', CITATION.cff has '1.2.3'" in out


def test_write_moves_the_version_and_keeps_the_rest(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, "0.1.0")
    code, out, _ = run("write", "--root", str(root))
    assert code == 0, out
    assert (root / TYPST_PATH).read_text(encoding="utf-8") == TYPST.format(version="1.2.3")
    assert (root / QUARTO_PATH).read_text(encoding="utf-8") == QUARTO.format(version="1.2.3")
    before = {path: (root / path).read_bytes() for path in (TYPST_PATH, QUARTO_PATH)}
    assert run("write", "--root", str(root))[0] == 0
    assert {path: (root / path).read_bytes() for path in (TYPST_PATH, QUARTO_PATH)} == before


def test_write_moves_authors_and_licence_when_opted_in(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, "1.2.3", '["author", "license"]')
    typst = root / TYPST_PATH
    typst.write_text(TYPST.format(version="1.2.3").replace('"Apache-2.0"', '"MIT"'), encoding="utf-8")
    quarto = root / QUARTO_PATH
    quarto.write_text(QUARTO.format(version="1.2.3").replace("Ada Lovelace", "Alan Turing"), encoding="utf-8")
    assert run("check", "--root", str(root))[0] == 1
    assert run("write", "--root", str(root))[0] == 0
    assert 'license = "Apache-2.0"' in typst.read_text(encoding="utf-8")
    assert "author: Ada Lovelace\n" in quarto.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", ["typst.toml", "_extension.yml", "_extension.yaml"])
def test_plugin_manifest_names_are_valid_manifests(tmp_path: Path, run: "Run", name: str) -> None:
    (tmp_path / "CITATION.cff").write_text((SYNTHETIC / "CITATION.cff").read_text(encoding="utf-8"), encoding="utf-8")
    (tmp_path / "plugin").mkdir()
    text = TYPST if name == "typst.toml" else QUARTO
    (tmp_path / "plugin" / name).write_text(text.format(version="0.1.0"), encoding="utf-8")
    config = f'manifests = ["plugin/{name}"]\nwrite-manifests = ["version"]\n'
    (tmp_path / "citesync.toml").write_text(config, encoding="utf-8")
    assert run("write", "--root", str(tmp_path))[0] == 0
    assert (tmp_path / "plugin" / name).read_text(encoding="utf-8") == text.format(version="1.2.3")
    code, out, err = run("check", "--root", str(tmp_path))
    assert (code, err) == (0, ""), out


def test_write_leaves_a_pre_release_out_of_typst_toml(tmp_path: Path, run: "Run") -> None:
    # Typst takes only major.minor.patch, so a pre-release would make the package unpublishable.
    root = _repo(tmp_path, "1.2.3")
    cff = root / "CITATION.cff"
    cff.write_text(cff.read_text(encoding="utf-8").replace('version: "1.2.3"', 'version: "1.3.0rc1"'), encoding="utf-8")
    code, out, _ = run("write", "--root", str(root))
    assert code == 1, out
    assert (root / TYPST_PATH).read_text(encoding="utf-8") == TYPST.format(version="1.2.3")
    assert "major.minor.patch only, not 1.3.0-rc.1" in out
    assert (root / QUARTO_PATH).read_text(encoding="utf-8") == QUARTO.format(version="1.3.0-rc.1")


def test_typst_toml_ignores_a_cargo_toml_above_it(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, "1.2.3")
    (root / "Cargo.toml").write_text("[package\nbroken", encoding="utf-8")
    (root / "citesync.toml").write_text(f'manifests = ["{TYPST_PATH}"]\n', encoding="utf-8")
    code, out, _ = run("check", "--root", str(root))
    assert code == 0, out

"""RO-Crate and Croissant files: compared with the source, never written."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.conftest import Run

CFF = """\
cff-version: 1.2.0
message: "If you use this software, please cite it as below."
title: "lensgrind"
abstract: "Grinds lenses."
version: "1.4.0"
date-released: 2026-10-31
authors:
  - given-names: "Marie"
    family-names: "Skłodowska-Curie"
    orcid: "https://orcid.org/0000-0002-1825-0097"
  - given-names: "Antonie"
    family-names: "van Leeuwenhoek"
doi: "10.5555/lensgrind"
license: "Apache-2.0"
keywords: ["optics", "microscopy"]
"""
CURIE = {
    "@id": "https://orcid.org/0000-0002-1825-0097",
    "@type": "Person",
    "givenName": "Marie",
    "familyName": "Skłodowska-Curie",
    "name": "Marie Skłodowska-Curie",
}
LEEUWENHOEK = {"@id": "#author-2", "@type": "Person", "givenName": "Antonie", "familyName": "van Leeuwenhoek"}
DESCRIBED = {
    "name": "lensgrind",
    "description": "Grinds lenses.",
    "version": "1.4.0",
    "license": "https://spdx.org/licenses/Apache-2.0",
    "identifier": "https://doi.org/10.5555/lensgrind",
    "datePublished": "2026-10-31",
    "keywords": ["optics", "microscopy"],
}


def _crate(**changes: object) -> dict:
    """An RO-Crate as sourceledger's release writes it: the root's authors are references to Person entities."""
    root: dict[str, object] = {
        "@id": "./",
        "@type": "Dataset",
        **DESCRIBED,
        "author": [{"@id": CURIE["@id"]}, {"@id": "#author-2"}],
    }
    root |= changes
    descriptor = {"@id": "ro-crate-metadata.json", "@type": "CreativeWork", "about": {"@id": "./"}}
    return {"@context": "https://w3id.org/ro/crate/1.3/context", "@graph": [descriptor, root, CURIE, LEEUWENHOEK]}


def _croissant(**changes: object) -> dict:
    """A Croissant file as sourceledger's release writes it: its people in place, under ``creator``."""
    return {"@type": "sc:Dataset", **DESCRIBED, "creator": [CURIE, LEEUWENHOEK]} | changes


MAKERS = {"ro-crate-metadata.json": _crate, "croissant.json": _croissant}


def _repo(tmp_path: Path, name: str, data: dict, *, under: str = "release/") -> Path:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / under).mkdir(exist_ok=True)
    (tmp_path / under / name).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    if under:
        (tmp_path / "citesync.toml").write_text(f'manifests = ["{under}{name}"]\n', encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("name", MAKERS)
def test_a_dataset_file_that_agrees_passes(name: str, tmp_path: Path, run: "Run") -> None:
    code, out, _ = run("check", "--root", str(_repo(tmp_path, name, MAKERS[name]())))
    assert code == 0, out


@pytest.mark.parametrize("name", MAKERS)
def test_a_drifted_dataset_file_fails_and_write_leaves_it(name: str, tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, name, MAKERS[name](version="1.3.0", license="https://spdx.org/licenses/MIT"))
    before = (root / "release" / name).read_bytes()
    code, out, _ = run("check", "--root", str(root))
    assert code == 1
    assert f"release/{name}" in out
    assert "version-mismatch" in out
    assert "license-mismatch" in out
    code, out, _ = run("write", "--root", str(root))
    assert code == 1
    assert (root / "release" / name).read_bytes() == before
    assert "made from codemeta.json" in out


def test_an_ro_crate_author_is_read_through_its_reference(tmp_path: Path, run: "Run") -> None:
    renamed = {**LEEUWENHOEK, "familyName": "Leeuwenhoek"}
    crate = _crate()
    crate["@graph"][3] = renamed
    code, out, _ = run("check", "--root", str(_repo(tmp_path, "ro-crate-metadata.json", crate)))
    assert code == 1
    assert "author-mismatch" in out


def test_a_bare_author_and_a_root_file_are_read(tmp_path: Path, run: "Run") -> None:
    """One author may be written without a list, and a file at the root is found with no config."""
    cff = CFF.split('  - given-names: "Antonie"', maxsplit=1)[0]
    croissant = _croissant(creator=CURIE)
    (tmp_path / "CITATION.cff").write_text(
        cff + 'doi: "10.5555/lensgrind"\nlicense: "Apache-2.0"\nkeywords: ["optics", "microscopy"]\n', encoding="utf-8"
    )
    (tmp_path / "croissant.json").write_text(json.dumps(croissant), encoding="utf-8")
    code, out, _ = run("check", "--root", str(tmp_path))
    assert code == 0, out
    (tmp_path / "croissant.json").write_text(json.dumps(croissant | {"name": "lensgrinder"}), encoding="utf-8")
    code, out, _ = run("check", "--root", str(tmp_path))
    assert code == 1
    assert "croissant.json" in out
    assert "name-mismatch" in out


def test_an_ro_crate_licence_entity_and_a_keyword_string_are_read(tmp_path: Path, run: "Run") -> None:
    licence = {"@id": "https://spdx.org/licenses/Apache-2.0", "@type": "CreativeWork", "name": "Apache License 2.0"}
    crate = _crate(license={"@id": licence["@id"]}, keywords="optics, microscopy")
    crate["@graph"].append(licence)
    code, out, _ = run("check", "--root", str(_repo(tmp_path, "ro-crate-metadata.json", crate)))
    assert code == 0, out


def test_an_ro_crate_without_a_root_entity_is_unreadable(tmp_path: Path, run: "Run") -> None:
    crate = _crate()
    crate["@graph"][1]["@id"] = "https://example.org/crate/"  # a detached crate, which the rows don't address
    code, out, _ = run("check", "--root", str(_repo(tmp_path, "ro-crate-metadata.json", crate)))
    assert code == 1
    assert "unreadable" in out
    assert "no root data entity" in out

"""Opt-in citation fields through the same CLI and config a maintainer uses."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from tests.conftest import Run


CFF = """cff-version: 1.2.0
message: If you use this software, please cite it.
title: Lens Observatory
abstract: A small optical benchmark.
version: 1.2.3
authors:
  - given-names: Ada
    family-names: Example
"""


def test_fill_selected_field_is_previewable_and_idempotent(tmp_path: Path, run: "Run") -> None:
    cff = tmp_path / "CITATION.cff"
    cff.write_text(CFF, encoding="utf-8")
    target = tmp_path / "codemeta.json"
    target.write_text('{"@context": "https://w3id.org/codemeta/3.0", "name" : "Lens Observatory"}\n', encoding="utf-8")
    other = tmp_path / ".zenodo.json"
    other.write_text('{"upload_type": "software", "title": "Lens Observatory"}\n', encoding="utf-8")
    args = ("--root", str(tmp_path))
    original = target.read_bytes()
    unselected = other.read_bytes()

    assert run("write", "--diff", *args) == (0, "", "")
    assert target.read_bytes() == original

    (tmp_path / "citesync.toml").write_text('[fill-missing]\n"codemeta.json" = ["version"]\n', encoding="utf-8")
    code, diff, _ = run("write", "--diff", *args)
    assert code == 1
    assert "codemeta.json" in diff
    assert '"version": "1.2.3"' in diff
    assert ".zenodo.json" not in diff
    assert target.read_bytes() == original
    assert other.read_bytes() == unselected

    assert run("write", *args)[0] == 0
    updated = target.read_text(encoding="utf-8")
    assert json.loads(updated) == dict(json.loads(original), version="1.2.3")
    assert '"name" : "Lens Observatory"' in updated
    assert cff.read_text(encoding="utf-8") == CFF
    assert other.read_bytes() == unselected
    assert run("write", "--diff", *args) == (0, "", "")


def test_fill_doi_preserves_a_structured_codemeta_identifier(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "CITATION.cff").write_text(CFF + "doi: 10.5555/lens-observatory\n", encoding="utf-8")
    target = tmp_path / "codemeta.json"
    old_identifier = (
        '{"@type":"PropertyValue", "propertyID" : "SWHID", '
        '"value": "swh:1:rev:0123456789abcdef0123456789abcdef01234567"}'
    )
    target.write_text(
        '{\n  "@context": "https://w3id.org/codemeta/3.0",\n'
        '  "name": "Lens Observatory",\n'
        f'  "identifier": [{old_identifier}]\n'
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "citesync.toml").write_text('[fill-missing]\n"codemeta.json" = ["identifier"]\n', encoding="utf-8")
    args = ("--root", str(tmp_path))

    assert run("write", *args)[0] == 0
    updated = target.read_text(encoding="utf-8")
    assert old_identifier in updated
    identifiers = json.loads(updated)["identifier"]
    assert identifiers[0] == json.loads(old_identifier)
    assert len(identifiers) == 2
    assert "10.5555/lens-observatory" in json.dumps(identifiers[1])
    assert run("check", "-q", *args) == (0, "", "")
    assert run("write", "--diff", *args) == (0, "", "")


def test_fill_nested_cff_from_explicit_source(tmp_path: Path, run: "Run") -> None:
    cff = tmp_path / "metadata" / "CITATION.cff"
    cff.parent.mkdir()
    cff.write_text(CFF.replace("version: 1.2.3\n", "") + "# preserved\n", encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(
        '{"@context": "https://w3id.org/codemeta/3.0", "name": "Lens Observatory", "version": "2.0.1"}\n',
        encoding="utf-8",
    )
    (tmp_path / "citesync.toml").write_text(
        'source = "codemeta.json"\nfiles = ["metadata/CITATION.cff"]\n'
        '[fill-missing]\n"metadata/CITATION.cff" = ["version", "codeRepository"]\n',
        encoding="utf-8",
    )

    assert run("write", "--root", str(tmp_path))[0] == 0
    updated = cff.read_text(encoding="utf-8")
    assert "2.0.1" in updated
    assert "# preserved" in updated
    assert "repository-code" not in updated


def test_fill_does_not_add_an_unrepresentable_zenodo_licence(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "CITATION.cff").write_text(CFF + "license: [MIT, Apache-2.0]\n", encoding="utf-8")
    target = tmp_path / ".zenodo.json"
    original = '{"upload_type": "software", "title": "Lens Observatory"}\n'
    target.write_text(original, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('[fill-missing]\n".zenodo.json" = ["license"]\n', encoding="utf-8")

    args = ("--root", str(tmp_path))
    code, out, err = run("write", "--diff", *args)
    assert code == 0
    assert not out
    assert "Zenodo takes one licence id" in err
    assert run("write", "--diff", "-q", *args) == (0, "", "")
    assert "Zenodo takes one licence id" in run("write", *args)[2]
    assert target.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("target", ["pyproject.toml", "ro-crate-metadata.json"])
def test_fill_config_rejects_non_citation_targets(tmp_path: Path, run: "Run", target: str) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(f'[fill-missing]\n"{target}" = ["version"]\n', encoding="utf-8")

    code, out, err = run("config", "--root", str(tmp_path))
    assert code == 3
    assert not out
    assert "fill-missing" in err
    assert target in err


def test_fill_uses_the_dataset_licence_for_configured_dataset_codemeta(tmp_path: Path, run: "Run") -> None:
    source = tmp_path / "CITATION.cff"
    source.write_text(CFF + "license: MIT\n", encoding="utf-8")
    dataset = tmp_path / "dataset.codemeta.json"
    dataset.write_text(
        '{"@context": "https://w3id.org/codemeta/3.0", "@type": "Dataset", "name": "Lens Observatory"}\n',
        encoding="utf-8",
    )
    (tmp_path / "citesync.toml").write_text(
        'dataset-license = "CC-BY-4.0"\n[fill-missing]\n"dataset.codemeta.json" = ["license"]\n',
        encoding="utf-8",
    )
    args = ("--root", str(tmp_path))
    original = source.read_bytes()

    assert run("write", *args)[0] == 0
    updated = json.loads(dataset.read_text(encoding="utf-8"))
    assert updated["license"] in {"CC-BY-4.0", "https://spdx.org/licenses/CC-BY-4.0"}
    assert source.read_bytes() == original
    assert run("write", "--diff", *args) == (0, "", "")


@pytest.mark.parametrize(
    ("target", "original"),
    [
        ("CITATION.cff", CFF + "identifiers: [{type: swh, value: pending}]\n"),
        (
            ".zenodo.json",
            '{"upload_type":"software","related_identifiers":[{"scheme":"swh","identifier":"pending"}]}\n',
        ),
    ],
)
def test_fill_does_not_duplicate_a_populated_unreadable_identifier(
    tmp_path: Path, run: "Run", target: str, original: str
) -> None:
    ref = "swh:1:rev:0123456789abcdef0123456789abcdef01234567"
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/3.0", "identifier": ref}),
        encoding="utf-8",
    )
    path = tmp_path / target
    path.write_text(original, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        f'source = "codemeta.json"\n[fill-missing]\n"{target}" = ["swhid"]\n', encoding="utf-8"
    )
    args = ("--root", str(tmp_path))
    assert run("write", "--diff", *args)[0] == 0
    assert run("write", *args)[0] == 0
    assert path.read_text(encoding="utf-8") == original


def test_check_counts_only_reported_fields_as_fixable(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(
        '{"@context":"https://w3id.org/codemeta/3.0","version":"1.0.0"}', encoding="utf-8"
    )
    (tmp_path / "citesync.toml").write_text('[fill-missing]\n"codemeta.json" = ["description"]\n', encoding="utf-8")
    args = ("--root", str(tmp_path))
    assert "1 fixable with `citesync write`" in run("check", *args)[1]
    assert "description" in run("write", "--diff", *args)[1]

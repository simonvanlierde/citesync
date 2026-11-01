"""Create explicitly requested Zenodo metadata without changing the source."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st
from ruamel.yaml import YAML

from citesync.config import Config
from citesync.formats import read_doc
from citesync.mapping import load_mapping
from citesync.write import write

if TYPE_CHECKING:
    from tests.conftest import Run

CFF = """\
cff-version: 1.2.0
message: Please cite this software.
title: lensgrind
abstract: Measure microscope optics.
authors:
  - given-names: Marie
    family-names: Skłodowska-Curie
    orcid: https://orcid.org/0000-0002-1825-0097
version: 1.4.0
license: Apache-2.0
date-released: 2026-10-31
doi: 10.5555/lensgrind
repository-code: https://example.org/lensgrind
keywords: [microscopy, optics]
identifiers:
  - type: swh
    value: swh:1:dir:0123456789abcdef0123456789abcdef01234567
"""


def _repo(root: Path, config: str = 'files = [".zenodo.json"]\n') -> Path:
    (root / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (root / "citesync.toml").write_text(config, encoding="utf-8")
    return root


@pytest.mark.parametrize("path", [".zenodo.json", "metadata/.zenodo.json"])
def test_create_zenodo_and_check_again(path: str, tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, f'files = ["{path}"]\n')
    code, out, err = run("write", "--root", str(root))
    assert (code, err) == (0, ""), out
    assert out.splitlines()[0] == f"wrote {path}"
    data = json.loads((root / path).read_text(encoding="utf-8"))
    assert data == {
        "upload_type": "software",
        "title": "lensgrind",
        "description": "Measure microscope optics.",
        "creators": [{"name": "Skłodowska-Curie, Marie", "orcid": "0000-0002-1825-0097"}],
        "version": "1.4.0",
        "license": "apache-2.0",
        "publication_date": "2026-10-31",
        "doi": "10.5555/lensgrind",
        "keywords": ["microscopy", "optics"],
        "related_identifiers": [
            {"identifier": "https://example.org/lensgrind", "relation": "isSupplementTo", "scheme": "url"},
            {
                "identifier": "swh:1:dir:0123456789abcdef0123456789abcdef01234567",
                "relation": "isIdenticalTo",
                "scheme": "swh",
            },
        ],
    }
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == CFF
    assert "Skłodowska-Curie" in (root / path).read_text(encoding="utf-8")
    before = (root / path).read_bytes()
    assert run("check", "-q", "--root", str(root)) == (0, "", "")
    assert run("write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / path).read_bytes() == before


def test_zenodo_creation_diff_does_not_write(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    code, out, err = run("write", "--diff", "--root", str(root))
    assert code == 1
    assert '+  "upload_type": "software"' in out
    assert "+++ b/.zenodo.json" in out
    assert "would fix 1 finding in 1 file" in err
    assert not (root / ".zenodo.json").exists()


@pytest.mark.parametrize("config", ["", 'ignore = ["file-missing"]\n'])
def test_zenodo_creation_requires_explicit_nonignored_request(config: str, tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, config if not config else 'files = [".zenodo.json"]\n' + config)
    assert run("write", "--root", str(root))[0] == 0
    assert not (root / ".zenodo.json").exists()


def test_zenodo_creation_requires_readable_source(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    (root / "CITATION.cff").write_text("title: [\n", encoding="utf-8")
    assert run("write", "--root", str(root))[0] == 1
    assert not (root / ".zenodo.json").exists()


def test_created_zenodo_omits_values_it_cannot_represent(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    (root / "CITATION.cff").write_text(CFF.replace("Apache-2.0", "MIT AND Apache-2.0"), encoding="utf-8")
    code, out, _ = run("write", "--root", str(root))
    assert code == 0, out
    assert "leaving out license: Zenodo takes one licence id" in out
    assert "license" not in json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))


def test_created_zenodo_explains_missing_contributor_type(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, 'source = "codemeta.json"\nfiles = [".zenodo.json"]\n')
    (root / "codemeta.json").write_text(
        json.dumps(
            {
                "@context": "https://w3id.org/codemeta/3.0",
                "name": "lensgrind",
                "author": [{"@type": "Person", "givenName": "Marie", "familyName": "Skłodowska-Curie"}],
                "contributor": [{"@type": "Person", "givenName": "Antonie", "familyName": "van Leeuwenhoek"}],
            }
        ),
        encoding="utf-8",
    )
    code, out, _ = run("write", "--root", str(root))
    assert code == 0, out
    assert "leaving out contributor: Zenodo needs a type" in out
    data = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    assert "contributors" not in data
    assert data["creators"] == [{"name": "Skłodowska-Curie, Marie"}]


@given(
    st.text(alphabet=st.characters(whitelist_categories=("L",), whitelist_characters="- '\""), min_size=1).filter(
        str.strip
    )
)
def test_new_zenodo_round_trips_names(name: str) -> None:
    import tempfile  # noqa: PLC0415

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        data = YAML(typ="safe").load(CFF)
        data["authors"] = [{"family-names": name}]
        with (root / "CITATION.cff").open("w", encoding="utf-8") as stream:
            YAML().dump(data, stream)
        mapping = load_mapping()
        source = read_doc(root, "CITATION.cff", mapping)
        texts, _, _, _ = write(root, Config(files=(".zenodo.json",)), mapping)
        assert ".zenodo.json" in texts
        created = read_doc(root, ".zenodo.json", mapping)
        assert created.record["author"] == source.record["author"]


def test_new_zenodo_does_not_invent_author_names(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    data = YAML(typ="safe").load(CFF)
    data["authors"] = [{"orcid": "https://orcid.org/0000-0002-1825-0097"}]
    with (root / "CITATION.cff").open("w", encoding="utf-8") as stream:
        YAML().dump(data, stream)
    code, out, _ = run("write", "--root", str(root))
    assert code == 0, out
    assert "leaving out author: Zenodo needs a name for each creator" in out
    assert "creators" not in json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))


def test_new_zenodo_keeps_an_organization_name(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    data = YAML(typ="safe").load(CFF)
    data["authors"] = [{"name": "Example Optics Institute"}]
    with (root / "CITATION.cff").open("w", encoding="utf-8") as stream:
        YAML().dump(data, stream)
    code, out, _ = run("write", "--root", str(root))
    assert code == 0, out
    assert json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))["creators"] == [
        {"name": "Example Optics Institute"}
    ]


@pytest.mark.parametrize(
    ("name", "content"),
    [
        (
            "pyproject.toml",
            (
                '[project]\nname = "lensgrind"\nversion = "1.4.0"\n'
                'authors = [{name = "Marie Skłodowska-Curie"}]\nlicense = "Apache-2.0"\n'
            ),
        ),
        (
            "Cargo.toml",
            (
                '[package]\nname = "lensgrind"\nversion = "1.4.0"\n'
                'authors = ["Marie Skłodowska-Curie"]\nlicense = "Apache-2.0"\n'
            ),
        ),
        (
            "package.json",
            json.dumps(
                {
                    "name": "lensgrind",
                    "version": "1.4.0",
                    "author": {"name": "Marie Skłodowska-Curie"},
                    "license": "Apache-2.0",
                }
            ),
        ),
    ],
)
def test_new_zenodo_can_take_each_package_manifest(name: str, content: str, tmp_path: Path, run: "Run") -> None:
    (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(f'source = "{name}"\nfiles = [".zenodo.json"]\n', encoding="utf-8")
    code, out, _ = run("write", "--root", str(tmp_path))
    assert code == 0, out
    data = json.loads((tmp_path / ".zenodo.json").read_text(encoding="utf-8"))
    assert data["creators"] == [{"name": "Skłodowska-Curie, Marie"}]
    assert data["title"] == "lensgrind"
    assert data["version"] == "1.4.0"
    assert data["license"] == "apache-2.0"
    assert set(data) == {"upload_type", "title", "version", "license", "creators"}
    assert (tmp_path / name).read_text(encoding="utf-8") == content
    assert run("check", "-q", "--root", str(tmp_path)) == (0, "", "")


def test_an_unsupported_missing_file_does_not_block_zenodo_creation(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "package.json").write_text('{"name": "lensgrind"}', encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'source = "package.json"\nfiles = ["CITATION.cff", ".zenodo.json"]\n', encoding="utf-8"
    )
    code, out, _ = run("write", "--root", str(tmp_path))
    assert code == 1
    assert "CITATION.cff: error[file-missing]" in out
    assert "wrote .zenodo.json" in out
    data = json.loads((tmp_path / ".zenodo.json").read_text(encoding="utf-8"))
    assert data == {"upload_type": "software", "title": "lensgrind"}
    assert not (tmp_path / "CITATION.cff").exists()

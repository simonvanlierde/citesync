"""Every fixture file reads into the record written by hand in its directory's record.json."""

import json
from pathlib import Path

import pytest

from citesync.formats import Doc, Person, read_doc
from citesync.mapping import load_mapping

FIXTURES = Path(__file__).parent / "fixtures"
CASES = [
    (repo.name, rel, expected)
    for repo in sorted(FIXTURES.glob("*/"))
    for rel, expected in json.loads((repo / "record.json").read_text(encoding="utf-8")).items()
]


def _person(person: Person) -> dict[str, str]:
    fields = {"name": person.name, "givenName": person.given, "familyName": person.family, "@id": person.orcid}
    return {key: value for key, value in fields.items() if value is not None}


def _plain(doc: Doc) -> dict[str, object]:
    record = {
        term: [_person(p) for p in value] if term == "author" else list(value) if isinstance(value, tuple) else value
        for term, value in doc.record.items()
    }
    return {"format": doc.format, "version": doc.version, "release": doc.release, "record": record}


@pytest.mark.parametrize(("repo", "rel", "expected"), CASES, ids=[f"{r}/{p}" for r, p, _ in CASES])
def test_reads_fixture(repo: str, rel: str, expected: dict[str, object]) -> None:
    assert _plain(read_doc(FIXTURES / repo, rel, load_mapping())) == expected


def test_every_fixture_file_has_a_record() -> None:
    """record.json lists every metadata file in the fixture, so none goes unread."""
    names = {"CITATION.cff", "codemeta.json", ".zenodo.json", "pyproject.toml", "Cargo.toml", "package.json"}
    on_disk = {
        (repo.name, str(path.relative_to(repo)))
        for repo in FIXTURES.glob("*/")
        for path in repo.rglob("*")
        if path.name in names
    }
    assert on_disk == {(repo, rel) for repo, rel, _ in CASES}


def test_cargo_member_without_workspace_drops_inherited_keys(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "x"\nversion.workspace = true\n', encoding="utf-8")
    assert read_doc(tmp_path, "Cargo.toml", load_mapping()).record == {"name": "x"}


def test_npm_person_string_and_codemeta_single_author(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text(
        '{"author": "Ada Lovelace <ada@example.org> (https://example.org)", "repository": "git+https://h/x.git"}',
        encoding="utf-8",
    )
    record = read_doc(tmp_path, "package.json", load_mapping()).record
    assert record == {"author": (Person("Ada Lovelace"),), "codeRepository": "https://h/x"}
    (tmp_path / "codemeta.json").write_text(
        '{"@context": ["https://w3id.org/codemeta/3.1", "https://schema.org"],'
        ' "author": {"givenName": "Ada", "familyName": "Lovelace"}}',
        encoding="utf-8",
    )
    doc = read_doc(tmp_path, "codemeta.json", load_mapping())
    assert (doc.version, doc.record["author"]) == ("3.1", (Person("Ada Lovelace", "Ada", "Lovelace"),))


def _read(tmp_path: Path, name: str, text: str) -> dict:
    (tmp_path / name).write_text(text, encoding="utf-8")
    return read_doc(tmp_path, name, load_mapping()).record


CFF = "cff-version: 1.2.0\nmessage: m\ntitle: x\n"


def test_cff_name_particle_suffix_and_entity(tmp_path: Path) -> None:
    record = _read(
        tmp_path,
        "CITATION.cff",
        CFF + "authors:\n"
        "  - {given-names: Simon, name-particle: van, family-names: Lierde}\n"
        "  - {given-names: Martin, family-names: King, name-suffix: Jr.}\n"
        "  - {name: ACME Lab}\n",
    )
    assert [p.name for p in record["author"]] == ["Simon van Lierde", "Martin King Jr.", "ACME Lab"]
    zenodo = _read(tmp_path, ".zenodo.json", '{"creators": [{"name": "van Lierde, Simon"}, {"name": "ACME Lab"}]}')
    assert [p.name for p in zenodo["author"]] == ["Simon van Lierde", "ACME Lab"]


def test_cff_scalars_read_as_written(tmp_path: Path) -> None:
    assert _read(tmp_path, "CITATION.cff", CFF + "version: 1.10\n")["version"] == "1.10"


def test_zenodo_repository_skips_a_doi_supplement(tmp_path: Path) -> None:
    related = [
        {"relation": "isSupplementTo", "identifier": "10.1/paper", "scheme": "doi"},
        {"relation": "isSupplementTo", "identifier": "https://github.com/o/r", "scheme": "url"},
    ]
    record = _read(tmp_path, ".zenodo.json", json.dumps({"related_identifiers": related}))
    assert record["codeRepository"] == "https://github.com/o/r"


def test_codemeta_identifier_url_or_list(tmp_path: Path) -> None:
    head = '{"@context": "https://w3id.org/codemeta/3.0", '
    assert "identifier" not in _read(tmp_path, "codemeta.json", head + '"identifier": "https://github.com/o/r"}')
    listed = _read(tmp_path, "codemeta.json", head + '"identifier": ["https://github.com/o/r", "10.1/a"]}')
    assert listed["identifier"] == "10.1/a"
    assert (
        _read(tmp_path, "codemeta.json", head + '"license": ["MIT", "Apache-2.0"]}')["license"] == "MIT OR Apache-2.0"
    )


def test_pep621_url_labels_are_normalised(tmp_path: Path) -> None:
    for label in ("homepage", "Source Code", "source-code", "repository"):
        text = f'[project]\nname = "x"\n[project.urls]\n"{label}" = "https://github.com/o/r"\n'
        assert _read(tmp_path, "pyproject.toml", text)["codeRepository"] == "https://github.com/o/r", label


def test_npm_bare_repository_is_github(tmp_path: Path) -> None:
    assert _read(tmp_path, "package.json", '{"repository": "o/r"}')["codeRepository"] == "https://github.com/o/r"

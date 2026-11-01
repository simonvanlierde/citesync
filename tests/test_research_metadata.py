"""Static R and Julia inputs retain citation data without evaluating package code."""

import json
import unicodedata
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from citesync.check import check
from citesync.config import Config
from citesync.errors import UnreadableError
from citesync.formats import load, read_doc
from citesync.mapping import load_mapping, resolve
from citesync.playground import generate
from citesync.write import write

if TYPE_CHECKING:
    from tests.conftest import Run

R = """Package: lensgrind
Title: Measure Microscope Optics
Version: 1.4-2
Description: Measure optics with a microscope.
    Keep the original measurements.
Authors@R: c(person("Marie", "Skłodowska-Curie", role = c("aut", "cre"),
    comment = c(ORCID = "0000-0002-1825-0097")),
    person("Grace", "Hopper", role = "ctb"),
    person("Ada", "Lovelace", role = "cre"))
License: GPL (>= 2)
URL: https://example.org/docs, https://github.com/simonvanlierde/citesync
Encoding: UTF-8
"""
JULIA = """name = "Lensgrind"
uuid = "00000000-0000-0000-0000-000000000001"
version = "1.4.2"
authors = [
  {given-names = "Marie", family-names = "Skłodowska-Curie", orcid = "0000-0002-1825-0097"},
  {name = "Example Lab"},
  "Antonie van Leeuwenhoek <optics@example.org>",
]
license = "MIT"
[deps]
"""


@pytest.mark.parametrize(
    ("filename", "text"), [("DESCRIPTION", R), ("Project.toml", JULIA), ("JuliaProject.toml", JULIA)]
)
def test_imports_create_citations_without_rewriting_the_source(filename: str, text: str, tmp_path: Path, run: "Run"):
    source = tmp_path / filename
    source.write_bytes(text.replace("\n", "\r\n").encode())
    before = source.read_bytes()
    code, out, err = run("init", "--source", filename, "--root", str(tmp_path))
    assert (code, err) == (0, ""), out
    config = Config(
        source=filename,
        files=("codemeta.json", ".zenodo.json"),
        manifests=(),
        zenodo_contributor_type="Other",
        codemeta_version="4.0",
    )
    write(tmp_path, config)
    data = json.loads((tmp_path / "codemeta.json").read_text())
    assert data["name"] == ("lensgrind: Measure Microscope Optics" if filename == "DESCRIPTION" else "Lensgrind")
    assert data["author"][0]["familyName"] == "Skłodowska-Curie"
    assert data["author"][0]["@id"] == "https://orcid.org/0000-0002-1825-0097"
    assert "00000000-0000-0000-0000-000000000001" not in json.dumps(data)
    assert source.read_bytes() == before
    assert write(tmp_path, config)[0] == {}
    assert not read_doc(tmp_path, filename, load_mapping()).is_citation
    assert not any(f.rule == "context-mismatch" for f in check(tmp_path, config)[0])
    result = generate({"filename": filename, "text": text})
    assert "Skłodowska-Curie" in unicodedata.normalize("NFC", result["files"]["CITATION.cff"])
    if filename == "DESCRIPTION":
        assert data["contributor"][0]["familyName"] == "Hopper"
        assert "Lovelace" not in json.dumps(data)
        assert json.loads(result["files"]["codemeta.json"])["contributor"][0]["familyName"] == "Hopper"


@pytest.mark.parametrize(
    ("title", "name"),
    [("Title: Measure Microscope Optics\n", "lensgrind: Measure Microscope Optics"), ("", "lensgrind")],
)
def test_r_name_is_package_and_title_as_r_tools_write_it(title: str, name: str, tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(f"Package: lensgrind\n{title}Version: 1.0\n")
    assert read_doc(tmp_path, "DESCRIPTION", load_mapping()).record["name"] == name


def test_julia_fields_outside_its_spec_are_not_read(tmp_path: Path):
    (tmp_path / "Project.toml").write_text(JULIA.replace("[deps]", 'description = "Grinds lenses."\n[deps]'))
    record = read_doc(tmp_path, "Project.toml", load_mapping()).record
    assert "license" not in record
    assert "description" not in record


@pytest.mark.parametrize(
    "expression",
    [
        'system("touch marker")',
        'readRDS("authors.rds")',
        'person(given=paste("Marie"), family="Curie", role="aut")',
        'c(person("Marie", "Curie", role="aut")); system("x")',
        "(" * 70 + 'person("Marie")' + ")" * 70,
    ],
)
def test_dynamic_or_unbounded_r_expressions_are_rejected(expression: str, tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text("Package: lensgrind\nVersion: 1.0\nAuthors@R: " + expression)
    with pytest.raises(UnreadableError, match="Authors@R"):
        read_doc(tmp_path, "DESCRIPTION", load_mapping())
    assert not (tmp_path / "marker").exists()


@pytest.mark.parametrize(
    "text",
    ["Package: lensgrind\nPackage: other", "Package: lensgrind\nbroken", " stray continuation", R + "\nPackage: other"],
)
def test_malformed_dcf_is_rejected(text: str, tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(text)
    with pytest.raises(UnreadableError):
        read_doc(tmp_path, "DESCRIPTION", load_mapping())


def test_r_maintainer_and_legacy_prose_are_not_invented_as_authors(tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(
        "Package: lensgrind\nVersion: 1.0\nAuthor: Example Lab and others\n"
        "Maintainer: Ada Lovelace <ada@example.org>\nLicense: MIT + file LICENSE\n"
    )
    doc = read_doc(tmp_path, "DESCRIPTION", load_mapping())
    assert "author" not in doc.record
    assert "license" not in doc.record
    assert doc.import_notes


def test_r_roles_without_aut_are_not_promoted(tmp_path: Path):
    text = R.replace('role = c("aut", "cre")', 'role = "cre"')
    (tmp_path / "DESCRIPTION").write_text(text)
    doc = read_doc(tmp_path, "DESCRIPTION", load_mapping())
    assert "author" not in doc.record
    assert len(doc.record["contributor"]) == 1


@pytest.mark.parametrize("authors", ["42", "[42]", "[{given-names=12}]", '[{name="Example Lab", given-names="Marie"}]'])
def test_invalid_julia_author_shapes_are_actionable(authors: str, tmp_path: Path):
    (tmp_path / "Project.toml").write_text('name="Lensgrind"\nauthors=' + authors)
    with pytest.raises(UnreadableError, match="author"):
        read_doc(tmp_path, "Project.toml", load_mapping())


def test_julia_cff_name_particle_and_missing_optional_fields(tmp_path: Path):
    text = 'name="Lensgrind"\nauthors=[{given-names="Antonie", family-names="Leeuwenhoek", name-particle="van"}]'
    (tmp_path / "Project.toml").write_text(text)
    doc = read_doc(tmp_path, "Project.toml", load_mapping())
    assert doc.record["author"][0].family == "van Leeuwenhoek"
    assert "version" not in doc.record
    assert "identifier" not in doc.record


def test_non_package_julia_environment_transfers_as_a_partial_draft():
    result = generate({"filename": "Project.toml", "text": "[deps]\n", "edit": True})
    assert result["details"]["title"] == ""
    assert result["details"]["authors"] == []


@pytest.mark.parametrize("filename", ["DESCRIPTION", "Project.toml", "JuliaProject.toml"])
def test_import_sources_cannot_be_written_even_with_direct_manifest_opt_in(filename: str, tmp_path: Path):
    text = R if filename == "DESCRIPTION" else JULIA
    (tmp_path / filename).write_text(text)
    (tmp_path / "codemeta.json").write_text('{"@context":"https://w3id.org/codemeta/3.0","version":"9.0"}')
    before = (tmp_path / filename).read_bytes()
    config = Config(source="codemeta.json", manifests=(filename,), write_manifests=("version",))
    assert write(tmp_path, config)[0] == {}
    assert (tmp_path / filename).read_bytes() == before


@pytest.mark.parametrize(
    ("license_text", "expected"),
    [
        ("GPL-2", "GPL-2.0-only"),
        ("GPL (>= 3)", "GPL-3.0-or-later"),
        ("LGPL (== 2.1)", "LGPL-2.1-only"),
        ("BSD_2_clause | MIT", "BSD-2-Clause OR MIT"),
        ("Artistic-2.0", "Artistic-2.0"),
    ],
)
def test_r_licence_spellings_have_explicit_meaning(license_text: str, expected: str, tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(R.replace("GPL (>= 2)", license_text))
    assert read_doc(tmp_path, "DESCRIPTION", load_mapping()).record["license"] == expected


@pytest.mark.parametrize("license_text", ["GPL", "file LICENSE", "GPL-2 + file LICENSE", "LicenseRef-example"])
def test_ambiguous_or_external_r_licences_are_not_guessed(license_text: str, tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(R.replace("GPL (>= 2)", license_text))
    doc = read_doc(tmp_path, "DESCRIPTION", load_mapping())
    assert "license" not in doc.record
    assert any(term == "license" for term, _ in doc.import_notes)


@pytest.mark.parametrize(
    "expression",
    [
        'person("Marie", "Curie", given="Other", role="aut")',
        'person("Marie", "Curie", role="aut", comment=c(ORCID="bad"))',
        'person("Marie", "Curie", role="aut", comment=c(ORCID="0000-0002-1825-0097", ORCID="0000-0002-1825-0097"))',
        'person("Marie", "Curie", role=42)',
        'person(NULL, NULL, role="aut")',
        'person("Marie", "Curie", role="aut", comment=person("Other"))',
        'c(person("Marie", "Curie", role="aut"), "other")',
        'person("\\ud800", "Curie", role="aut")',
    ],
)
def test_bad_static_person_values_are_actionable(expression: str, tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text("Package: lensgrind\nAuthors@R: " + expression)
    with pytest.raises(UnreadableError):
        read_doc(tmp_path, "DESCRIPTION", load_mapping())


def test_r_name_vectors_and_literal_quotes_are_retained(tmp_path: Path):
    text = """Package: lensgrind
Authors@R: person(given=c('Marie', 'Salomea'), family="Skłodowska-Curie", role="aut")
"""
    (tmp_path / "DESCRIPTION").write_text(text)
    person = read_doc(tmp_path, "DESCRIPTION", load_mapping()).record["author"][0]
    assert person.given == "Marie Salomea"
    assert person.family == "Skłodowska-Curie"


def test_r_never_labels_a_homepage_as_a_repository(tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(
        R.replace("https://example.org/docs, https://github.com/simonvanlierde/citesync", "https://example.org/docs")
    )
    doc = read_doc(tmp_path, "DESCRIPTION", load_mapping())
    assert "codeRepository" not in doc.record
    assert any(term == "codeRepository" for term, _ in doc.import_notes)


def test_explicit_empty_julia_author_and_partial_r_drafts_transfer():
    result = generate({"filename": "DESCRIPTION", "text": "Package: lensgrind\nAuthor: prose", "edit": True})
    assert result["details"]["title"] == "lensgrind"
    assert result["details"]["authors"] == []


def test_non_iso_r_date_is_omitted_with_a_notice(tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(R + "Date: yesterday\n")
    doc = read_doc(tmp_path, "DESCRIPTION", load_mapping())
    assert "datePublished" not in doc.record
    assert any(term == "datePublished" for term, _ in doc.import_notes)


def test_iso_r_date_and_julia_entity_are_preserved(tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(R + "Date: 2026-10-31\n")
    assert read_doc(tmp_path, "DESCRIPTION", load_mapping()).record["datePublished"] == "2026-10-31"
    result = generate({"filename": "Project.toml", "text": JULIA})
    organization = json.loads(result["files"]["codemeta.json"])["author"][1]
    assert organization["@type"] == "Organization"
    assert organization["name"] == "Example Lab"


@pytest.mark.parametrize("text", ['uuid="bad"', "name=42", 'authors=[{orcid="bad", given-names="Marie"}]', "[broken"])
def test_invalid_julia_scalar_values_are_rejected(text: str, tmp_path: Path):
    (tmp_path / "Project.toml").write_text(text)
    with pytest.raises(UnreadableError):
        read_doc(tmp_path, "Project.toml", load_mapping())


@given(st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=30))
def test_unicode_r_names_survive_static_import(name: str):
    text = (
        "Package: lensgrind\nVersion: 1.0\nAuthors@R: person("
        + json.dumps(name, ensure_ascii=False)
        + ', "Curie", role="aut")'
    )
    result = generate({"filename": "DESCRIPTION", "text": text})
    assert unicodedata.normalize("NFC", name) in unicodedata.normalize("NFC", result["files"]["CITATION.cff"])


@given(st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=30))
def test_unicode_julia_names_survive_import(name: str):
    text = 'name="Lensgrind"\nauthors=[' + json.dumps(name, ensure_ascii=False) + "]"
    result = generate({"filename": "Project.toml", "text": text})
    assert unicodedata.normalize("NFC", name) in unicodedata.normalize("NFC", result["files"]["CITATION.cff"])


def test_malformed_r_repository_url_is_reported_not_crashed(tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text("Package: lensgrind\nURL: https://[broken\n")
    with pytest.raises(UnreadableError, match="URL"):
        read_doc(tmp_path, "DESCRIPTION", load_mapping())


def test_r_author_who_also_contributed_is_one_author_not_a_contributor(tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(R.replace('role = c("aut", "cre")', 'role = c("aut", "ctb")'))
    record = read_doc(tmp_path, "DESCRIPTION", load_mapping()).record
    assert [person.family for person in record["author"]] == ["Skłodowska-Curie"]
    assert [person.family for person in record["contributor"]] == ["Hopper"]


def test_description_reads_through_the_r_description_rows(tmp_path: Path):
    (tmp_path / "DESCRIPTION").write_text(R + "Date: 2026-10-31\n")
    data, mapping = load(tmp_path / "DESCRIPTION", "DESCRIPTION"), load_mapping()

    def at(term: str) -> list:
        return resolve(data, str(mapping["r-description", term]))

    assert at("name") == ["lensgrind: Measure Microscope Optics"]
    assert at("version") == ["1.4-2"]
    assert at("author.givenName") == ["Marie"]
    assert at("author.familyName") == ["Skłodowska-Curie"]
    assert at("author.@id") == ["https://orcid.org/0000-0002-1825-0097"]
    assert at("contributor.familyName") == ["Hopper"]
    assert at("license") == ["GPL-2.0-or-later"]
    assert at("codeRepository") == ["https://github.com/simonvanlierde/citesync"]
    assert at("datePublished") == ["2026-10-31"]
    assert read_doc(tmp_path, "DESCRIPTION", mapping).format == "r-description"


def test_project_toml_reads_through_the_julia_rows(tmp_path: Path):
    (tmp_path / "Project.toml").write_text(JULIA)
    data, mapping = load(tmp_path / "Project.toml", "Project.toml"), load_mapping()

    def at(term: str) -> list:
        return resolve(data, str(mapping["julia", term]))

    assert at("name") == ["Lensgrind"]
    assert at("version") == ["1.4.2"]
    assert len(at("author")) == 3
    assert at("author.familyName") == ["Skłodowska-Curie"]
    assert at("author.@id") == ["0000-0002-1825-0097"]
    doc = read_doc(tmp_path, "Project.toml", mapping)
    assert doc.format == "julia"
    assert [p.name for p in doc.record["author"]] == [
        "Marie Skłodowska-Curie",
        "Example Lab",
        "Antonie van Leeuwenhoek",
    ]
    assert [p.organization for p in doc.record["author"]] == [False, True, False]

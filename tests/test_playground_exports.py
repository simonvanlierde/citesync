import json
import tomllib

from hypothesis import example, given
from hypothesis import strategies as st

from citesync.formats import Person
from citesync.playground_exports import bibliography, package_templates, tex


def test_bibtex_escapes_literal_metadata_and_keeps_organisation_together():
    assert tex("\\{}&%$#_~^") == (r"\textbackslash{}\{\}\&\%\$\#\_\textasciitilde{}\textasciicircum{}")
    files, notes = bibliography(
        {
            "name": "lensgrind {optics}",
            "author": (Person("Example Optics Institute", organization=True),),
            "identifier": "10.5555/lensgrind",
            "datePublished": "2026-10-31",
        }
    )
    assert "author = {{Example Optics Institute}}" in files["citation.bib"]
    csl = json.loads(files["citation.csl.json"])[0]
    assert csl["issued"] == {"date-parts": [[2026, 10, 31]]}
    assert csl["DOI"] == "10.5555/lensgrind"
    assert csl["author"] == [{"literal": "Example Optics Institute"}]
    assert notes == []


def test_templates_omit_unusable_names_and_versions_without_inventing_replacements():
    templates, notes = package_templates({"name": "Lens Grind", "version": "nightly"})
    for data in (
        tomllib.loads(templates["pyproject.toml"])["project"],
        tomllib.loads(templates["Cargo.toml"])["package"],
        json.loads(templates["package.json"]),
    ):
        assert "name" not in data
        assert "version" not in data
        assert "dependencies" not in data
    assert len(notes) == 6
    assert json.loads(templates["package.json"])["private"] is True
    assert "build-system" not in tomllib.loads(templates["pyproject.toml"])


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=80))
@example("Quotes \" and ' and \\paths\nnew line\r\t")
def test_package_serializers_round_trip_description(text: str):
    templates, _ = package_templates({"name": "lensgrind", "description": text})
    assert tomllib.loads(templates["pyproject.toml"])["project"]["description"] == text
    assert tomllib.loads(templates["Cargo.toml"])["package"]["description"] == text
    assert json.loads(templates["package.json"])["description"] == text


def test_bibtex_is_readable_by_an_independent_parser():
    from pybtex.database import parse_string  # noqa: PLC0415

    files, _ = bibliography(
        {
            "name": "lensgrind {optics} & \\ calibration",
            "author": (
                Person("Antonie van Leeuwenhoek", given="Antonie", family="van Leeuwenhoek"),
                Person("Example Optics Institute", organization=True),
            ),
        }
    )
    entry = parse_string(files["citation.bib"], "bibtex").entries["software"]
    assert entry.type == "misc"
    assert len(entry.persons["author"]) == 2
    assert entry.persons["author"][0].last_names == ["{van Leeuwenhoek}"]
    assert entry.persons["author"][0].first_names == ["{Antonie}"]
    assert entry.persons["author"][1].last_names == ["{Example Optics Institute}"]

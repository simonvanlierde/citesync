"""The exports: each format's text, the ``exports`` setting, and check and write keeping the files in step."""

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from citesync.config import load_config
from citesync.errors import CheckError
from citesync.export import citations, key, render, tex
from citesync.formats import Person

if TYPE_CHECKING:
    from tests.conftest import Run

FIXTURES = Path(__file__).parent / "fixtures"
CURIE = Person("Marie Skłodowska-Curie", given="Marie", family="Skłodowska-Curie", orcid="0000-0002-1825-0097")
LEEUWENHOEK = Person("Antonie van Leeuwenhoek", given="Antonie", family="van Leeuwenhoek")
TU = Person("Tu Youyou", given="Youyou", family="Tu")
LAB = Person("Example Optics Institute", organization=True)
LENSGRIND = {
    "name": "lensgrind",
    "version": "1.4.0",
    "author": (CURIE, LEEUWENHOEK),
    "identifier": "10.5555/lensgrind",
    "codeRepository": "https://example.org/lensgrind",
    "datePublished": "2026-10-31",
    "license": "Apache-2.0",
    "keywords": ("optics", "microscopy"),
}


def test_bibtex_escapes_literal_metadata_and_keeps_organisation_together() -> None:
    assert tex("\\{}&%$#_~^") == (r"\textbackslash{}\{\}\&\%\$\#\_\textasciitilde{}\textasciicircum{}")
    files, notes = citations(
        {
            "name": "lensgrind {optics}",
            "author": (LAB,),
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


def test_bibtex_is_readable_by_an_independent_parser() -> None:
    from pybtex.database import parse_string  # noqa: PLC0415

    bib = render("bibtex", {"name": "lensgrind {optics} & \\ calibration", "author": (LEEUWENHOEK, LAB)})[0]
    entry = parse_string(bib, "bibtex").entries["lensgrind-optics-calibration"]
    assert entry.type == "misc"
    assert len(entry.persons["author"]) == 2
    assert entry.persons["author"][0].last_names == ["{van Leeuwenhoek}"]
    assert entry.persons["author"][0].first_names == ["{Antonie}"]
    assert entry.persons["author"][1].last_names == ["{Example Optics Institute}"]


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("CRediT Matrix", "credit-matrix"),
        ("CRediT Matrix: drafting CRediT contribution statements", "credit-matrix"),
        ("lensgrind - optics", "lensgrind"),
        ("Skłodowska tools", "sklodowska-tools"),
        ("屠呦呦", "software"),
    ],
)
def test_key_is_the_title_before_any_subtitle(title: str, expected: str) -> None:
    assert key({"name": title}) == expected


def test_apa_reference() -> None:
    assert render("apa", LENSGRIND)[0] == (
        "Skłodowska-Curie, M., & van Leeuwenhoek, A. (2026). lensgrind (Version 1.4.0) [Computer software]."
        " https://doi.org/10.5555/lensgrind\n"
    )


@pytest.mark.parametrize(
    ("people", "authors"),
    [
        ((TU,), "Tu, Y."),
        ((LAB,), "Example Optics Institute."),
        ((Person("Jean-Baptiste Lamarck", given="Jean-Baptiste", family="Lamarck"),), "Lamarck, J.-B."),
        ((TU, LAB, CURIE), "Tu, Y., Example Optics Institute, & Skłodowska-Curie, M."),
        (
            tuple(Person(f"Given{i} Family{i}", given=f"G{i}", family=f"Family{i}") for i in range(22)),
            ", ".join(f"Family{i}, G." for i in range(19)) + ", . . . Family21, G.",
        ),
    ],
)
def test_apa_author_lists(people: tuple[Person, ...], authors: str) -> None:
    text = render("apa", {"name": "lensgrind", "author": people, "datePublished": "2026-10-31"})[0]
    assert text == f"{authors} (2026). lensgrind [Computer software].\n"


def test_apa_without_author_date_or_doi() -> None:
    text, notes = render("apa", {"name": "lensgrind", "codeRepository": "https://example.org/lensgrind"})
    assert text == "lensgrind [Computer software]. (n.d.). https://example.org/lensgrind\n"
    assert notes == []
    assert render("apa", {"name": "lensgrind", "author": (TU,), "datePublished": "Oct 2026"})[1] == [
        "BibTeX, CSL-JSON and APA: release date omitted because it is not a YYYY, YYYY-MM or YYYY-MM-DD date."
    ]


def test_a_year_alone_is_a_release_date() -> None:
    rec = {"name": "lensgrind", "author": (TU,), "datePublished": "2026"}
    assert render("apa", rec) == ("Tu, Y. (2026). lensgrind [Computer software].\n", [])
    assert "  year = {2026},\n" in render("bibtex", rec)[0]
    assert json.loads(render("csl-json", rec | {"datePublished": "2026-10"})[0])[0]["issued"] == {
        "date-parts": [[2026, 10]]
    }
    assert render("apa", rec | {"datePublished": "2026-02-30"})[0].startswith("Tu, Y. (n.d.).")


def test_apa_initials_are_capitals() -> None:
    elise = Person("élise Dupont", given="élise", family="Dupont")
    assert render("apa", {"name": "x", "author": (elise,)})[0].startswith("Dupont, É. (n.d.).")


def test_bibtex_doi_and_url_stay_verbatim() -> None:
    bib = render("bibtex", {"name": "x", "identifier": "10.5555/a_b", "codeRepository": "https://example.com/a%20b#x"})[
        0
    ]
    assert "  doi = {10.5555/a_b},\n" in bib
    assert "  url = {https://example.com/a%20b#x},\n" in bib


def test_jsonld_is_plain_schema_org() -> None:
    data = json.loads(render("jsonld", LENSGRIND | {"contributor": (LAB,)})[0])
    assert data == {
        "@context": "https://schema.org",
        "@type": "SoftwareSourceCode",
        "name": "lensgrind",
        "version": "1.4.0",
        "codeRepository": "https://example.org/lensgrind",
        "datePublished": "2026-10-31",
        "identifier": "https://doi.org/10.5555/lensgrind",
        "license": "https://spdx.org/licenses/Apache-2.0",
        "keywords": ["optics", "microscopy"],
        "author": [
            {
                "@type": "Person",
                "@id": "https://orcid.org/0000-0002-1825-0097",
                "givenName": "Marie",
                "familyName": "Skłodowska-Curie",
                "name": "Marie Skłodowska-Curie",
            },
            {
                "@type": "Person",
                "givenName": "Antonie",
                "familyName": "van Leeuwenhoek",
                "name": "Antonie van Leeuwenhoek",
            },
        ],
        "contributor": [{"@type": "Organization", "name": "Example Optics Institute"}],
    }
    assert json.loads(render("jsonld", {"name": "x", "license": "MIT OR Apache-2.0"})[0])["license"] == (
        "MIT OR Apache-2.0"
    )


def test_credit_matrix_fixture_matches_its_about_page() -> None:
    """The APA reference credit-matrix's About page builds by hand (src/lib/citation.ts), for its CITATION.cff."""
    from citesync.check import read_docs  # noqa: PLC0415
    from citesync.config import Config  # noqa: PLC0415
    from citesync.export import record  # noqa: PLC0415
    from citesync.mapping import load_mapping  # noqa: PLC0415

    docs, _ = read_docs(FIXTURES / "credit-matrix", Config(manifests=()), load_mapping())
    rec = record(docs) | {"name": "CRediT Matrix"}  # the fixture predates the title fix
    assert render("apa", rec)[0] == (
        "van Lierde, S. (2026). CRediT Matrix (Version 0.8.1) [Computer software]."
        " https://doi.org/10.5281/zenodo.21213659\n"
    )


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ('["citation.txt"]', "must end in one of .csl.json, .apa.txt, .bib, .jsonld"),
        ('[".bib"]', "must end in one of"),
        ('["../citation.bib"]', "must be relative to the repo root"),
        ('"citation.bib"', "exports must be a list of paths"),
    ],
)
def test_exports_setting_is_validated(tmp_path: Path, value: str, message: str) -> None:
    (tmp_path / "citesync.toml").write_text(f"exports = {value}\n", encoding="utf-8")
    with pytest.raises(CheckError, match=message):
        load_config(tmp_path)


EXPORTS = ["citation.bib", "citation.csl.json", "docs/citation.apa.txt", "schema.jsonld"]


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "synthetic-agree", root)
    (root / "citesync.toml").write_text(f"exports = {json.dumps(EXPORTS)}\n", encoding="utf-8")
    return root


def test_check_reports_and_write_makes_each_export(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    code, out, _ = run("check", "--root", str(root))
    assert code == 1
    assert out.count("error[export-stale] missing") == len(EXPORTS)
    code, out, _ = run("write", "--root", str(root))
    assert code == 0, out
    for path in EXPORTS:
        assert f"wrote {path}" in out
        expected = run("export", "--root", str(root), "--format", _FORMAT[Path(path).name])[1]
        assert (root / path).read_text(encoding="utf-8") == expected
    before = {path: (root / path).read_bytes() for path in EXPORTS}
    assert run("write", "--root", str(root))[0] == 0
    assert {path: (root / path).read_bytes() for path in EXPORTS} == before
    assert run("check", "--root", str(root))[0] == 0


def test_an_edited_export_is_stale_and_write_puts_it_back(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    run("write", "--root", str(root))
    made = (root / "citation.bib").read_text(encoding="utf-8")
    (root / "citation.bib").write_text(made.replace("year", "yeer"), encoding="utf-8")
    (root / "schema.jsonld").write_bytes((root / "schema.jsonld").read_bytes().replace(b"\n", b"\r\n"))
    code, out, _ = run("check", "--root", str(root))
    assert code == 1
    assert "citation.bib: error[export-stale] differs from what the source gives" in out
    assert "schema.jsonld" not in out  # CRLF line ends alone don't make an export stale
    run("write", "--root", str(root))
    assert (root / "citation.bib").read_text(encoding="utf-8") == made


def test_export_follows_a_source_change(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    run("write", "--root", str(root))
    cff = root / "CITATION.cff"
    cff.write_text(cff.read_text(encoding="utf-8").replace('version: "1.2.3"', 'version: "1.3.0"'), encoding="utf-8")
    assert "(Version 1.3.0)" in run("export", "--root", str(root), "--format", "apa")[1]
    assert "docs/citation.apa.txt: error[export-stale]" in run("check", "--root", str(root))[1]


def test_ignored_export_stale_is_never_written(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    (root / "citesync.toml").write_text('exports = ["citation.bib"]\nignore = ["export-stale"]\n', encoding="utf-8")
    assert run("check", "--root", str(root))[0] == 0
    run("write", "--root", str(root))
    assert not (root / "citation.bib").exists()


def test_no_title_is_a_finding_not_a_crash(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "codemeta.json").write_text('{"@context": "https://w3id.org/codemeta/3.0"}', encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('source = "codemeta.json"\nexports = ["citation.bib"]\n', encoding="utf-8")
    code, out, _ = run("check", "--root", str(tmp_path))
    assert code == 1
    assert "citation.bib: error[export-stale] can't be made: no file gives a title" in out
    assert run("write", "--root", str(tmp_path))[0] == 1
    assert not (tmp_path / "citation.bib").exists()
    code, _, err = run("export", "--root", str(tmp_path), "--format", "bibtex")
    assert (code, err) == (2, "citesync: no file gives a title, which a citation needs\n")


def test_an_export_outside_the_root_or_a_directory_is_never_read_or_written(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "citation.apa.txt").write_text("hi\n", encoding="utf-8")
    (root / "out").symlink_to(elsewhere)
    (root / "dir.jsonld").mkdir()
    exports = '["citation.bib", "out/citation.apa.txt", "dir.jsonld"]'
    (root / "citesync.toml").write_text(f"exports = {exports}\n", encoding="utf-8")
    code, out, _ = run("check", "--root", str(root))
    assert code == 1
    for path in ("out/citation.apa.txt", "dir.jsonld"):
        assert f"{path}: error[export-stale] can't be written: not a file inside the repo root" in out
    code, out, err = run("write", "--diff", "--root", str(root))
    assert "hi" not in out
    assert "unexpected error" not in err
    code, out, err = run("write", "--root", str(root))
    assert code == 1
    assert "unexpected error" not in err
    assert (root / "citation.bib").is_file()
    assert (elsewhere / "citation.apa.txt").read_text(encoding="utf-8") == "hi\n"


def test_export_command_needs_a_readable_source(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "CITATION.cff").write_text("cff-version: [\n", encoding="utf-8")
    code, out, err = run("export", "--root", str(tmp_path), "--format", "apa")
    assert (code, out) == (2, "")
    assert err.startswith("citesync: CITATION.cff")


_FORMAT = {
    "citation.bib": "bibtex",
    "citation.csl.json": "csl-json",
    "citation.apa.txt": "apa",
    "schema.jsonld": "jsonld",
}

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


def _many(n: int) -> tuple[Person, ...]:
    return tuple(Person(f"G{i} Family{i}", given=f"G{i}", family=f"Family{i}") for i in range(n))


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
    assert entry.type == "software"
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
        ("lensgrind \u2014 optics", "lensgrind"),
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
        (_many(20), ", ".join(f"Family{i}, G." for i in range(19)) + ", & Family19, G."),
        (_many(21), ", ".join(f"Family{i}, G." for i in range(19)) + ", . . . Family20, G."),
        (_many(22), ", ".join(f"Family{i}, G." for i in range(19)) + ", . . . Family21, G."),
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
    from pybtex.database import parse_string  # noqa: PLC0415

    bib = render("bibtex", {"name": "x", "identifier": "10.5555/a_b", "codeRepository": "https://example.com/a%20b#x"})[
        0
    ]
    assert "  doi = {10.5555/a_b},\n" in bib
    assert "  url = {https://example.com/a%20b#x},\n" in bib
    braced = render("bibtex", {"name": "x", "codeRepository": "https://example.com/a{b}"})[0]
    assert parse_string(braced, "bibtex").entries["x"].fields["url"] == "https://example.com/a%7Bb%7D"


def test_csl_and_bibtex_carry_the_version() -> None:
    assert json.loads(render("csl-json", LENSGRIND)[0])[0]["version"] == "1.4.0"
    assert "  version = {1.4.0},\n" in render("bibtex", LENSGRIND)[0]


def test_a_bad_date_is_noted_once_and_kept_in_jsonld() -> None:
    files, notes = citations(LENSGRIND | {"datePublished": "Oct 2026"})
    assert len(notes) == 1
    assert json.loads(files["schema.jsonld"])["datePublished"] == "Oct 2026"
    assert render("jsonld", LENSGRIND | {"datePublished": "Oct 2026"})[1] == []
    assert "year" not in files["citation.bib"]


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


def test_exports_setting_drops_duplicates(tmp_path: Path) -> None:
    (tmp_path / "citesync.toml").write_text('exports = ["./citation.bib", "citation.bib"]\n', encoding="utf-8")
    assert load_config(tmp_path).exports == ("citation.bib",)


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ('["citation.txt"]', "must end in one of .csl.json, .apa.txt, .bib, .jsonld"),
        ('[".bib"]', "must end in one of"),
        ('["../citation.bib"]', "must be relative to the repo root"),
        ('["/tmp/citation.bib"]', "must be relative to the repo root"),
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
    assert f"{len(EXPORTS)} fixed" in out
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
        assert f"{path}: error[export-stale] can't be written: a link, a folder, or under a file" in out
    code, out, err = run("write", "--diff", "--root", str(root))
    assert "+++ b/citation.bib" in out
    assert "out/citation.apa.txt" not in out
    assert "unexpected error" not in err
    code, out, err = run("write", "--root", str(root))
    assert code == 1
    assert "unexpected error" not in err
    assert (root / "citation.bib").is_file()
    assert (elsewhere / "citation.apa.txt").read_text(encoding="utf-8") == "hi\n"


@pytest.mark.parametrize("path", ["citation.bib", "pyproject.toml/c.bib"])
def test_a_link_or_a_path_under_a_file_is_never_written(tmp_path: Path, run: "Run", path: str) -> None:
    root = _repo(tmp_path)
    if path == "citation.bib":
        (root / path).symlink_to("CITATION.cff")  # write would put BibTeX over the source
    (root / "citesync.toml").write_text(f'exports = ["{path}", "citation.apa.txt"]\n', encoding="utf-8")
    cff = (root / "CITATION.cff").read_bytes()
    assert f"{path}: error[export-stale] can't be written" in run("check", "--root", str(root))[1]
    code, _, err = run("write", "--root", str(root))
    assert (code, "unexpected error" in err) == (1, False)
    assert (root / "CITATION.cff").read_bytes() == cff
    assert (root / "citation.apa.txt").is_file()


def test_jsonld_can_sit_in_a_script_tag() -> None:
    text = render("jsonld", {"name": "x</script><script>alert(1)</script>"})[0]
    assert "<" not in text
    assert json.loads(text)["name"] == "x</script><script>alert(1)</script>"


def test_cli_offers_every_export_format() -> None:
    from citesync.cli import _EXPORT_FORMATS  # noqa: PLC0415
    from citesync.export import SUFFIXES  # noqa: PLC0415

    assert set(_EXPORT_FORMATS) == set(SUFFIXES.values())


def test_a_term_the_source_lacks_comes_from_a_readable_file(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    cff = root / "CITATION.cff"
    cff.write_text(cff.read_text(encoding="utf-8").replace('version: "1.2.3"\n', ""), encoding="utf-8")
    (root / ".zenodo.json").write_text('{"title": ', encoding="utf-8")  # broken: it must give nothing
    code, out, err = run("export", "--root", str(root), "--format", "apa")
    assert (code, err) == (0, "")
    assert "(Version 1.2.3)" in out  # from codemeta.json


def test_export_notes_go_to_stderr(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    cff = root / "CITATION.cff"
    cff.write_text(
        cff.read_text(encoding="utf-8").replace("date-released: 2026-01-15", 'date-released: "Jan 2026"'),
        encoding="utf-8",
    )
    code, out, err = run("export", "--root", str(root), "--format", "bibtex")
    assert code == 0
    assert out.startswith("@software{synthagree,")
    assert "release date omitted" in err


def test_no_export_finding_while_the_source_is_unreadable(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    (root / "CITATION.cff").write_text("cff-version: [\n", encoding="utf-8")
    assert "export-stale" not in run("check", "--root", str(root))[1]


def test_export_findings_keep_the_other_findings(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path)
    (root / ".zenodo.json").write_text('{"title": ', encoding="utf-8")
    out = run("check", "--root", str(root))[1]
    assert "error[export-stale]" in out
    assert ".zenodo.json:1:11: error[unreadable]" in out


def test_export_command_needs_a_readable_source(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "CITATION.cff").write_text("cff-version: [\n", encoding="utf-8")
    code, out, err = run("export", "--root", str(tmp_path), "--format", "apa")
    assert (code, out) == (2, "")
    assert err.startswith("citesync: CITATION.cff")


@pytest.mark.parametrize(
    ("fmt", "name", "source"),
    [("cff", "CITATION.cff", "codemeta.json"), ("codemeta", "codemeta.json", None), ("zenodo", ".zenodo.json", None)],
)
def test_export_prints_a_citation_file_that_check_accepts(
    tmp_path: Path, run: "Run", fmt: str, name: str, source: str | None
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    start = source or "CITATION.cff"
    shutil.copy(FIXTURES / "synthetic-agree" / start, root / start)
    if source:
        (root / "citesync.toml").write_text(f'source = "{source}"\n', encoding="utf-8")
    before = sorted(p.name for p in root.iterdir())
    code, out, err = run("export", "--root", str(root), "--format", fmt)
    assert code == 0, err
    assert sorted(p.name for p in root.iterdir()) == before  # it writes nothing
    (root / name).write_text(out, encoding="utf-8")
    code, report, _ = run("check", "--root", str(root))
    assert code == 0, report


def test_export_follows_the_citation_file_settings(tmp_path: Path, run: "Run") -> None:
    root = tmp_path / "repo"
    shutil.copytree(FIXTURES / "synthetic-agree", root)
    (root / "citesync.toml").write_text(
        'codemeta-version = "2.0"\nzenodo-contributor-type = "Researcher"\n', encoding="utf-8"
    )
    codemeta = json.loads(run("export", "--root", str(root), "--format", "codemeta")[1])
    assert codemeta["@context"] == "https://w3id.org/codemeta/2.0"
    zenodo = json.loads(run("export", "--root", str(root), "--format", "zenodo")[1])
    assert zenodo["contributors"]
    assert {c["type"] for c in zenodo["contributors"]} == {"Researcher"}


PYPROJECT = """\
[project]
name = "lensgrind"
version = "1.0.0"
description = "Grinds lenses."
keywords = ["alpha"]
authors = [{name = "Antonie van Leeuwenhoek"}]
"""


def test_export_cff_is_the_file_init_writes(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    package = {"name": "lensgrind", "version": "1.0.0", "keywords": ["beta"], "author": "Antonie van Leeuwenhoek"}
    (tmp_path / "package.json").write_text(json.dumps(package), encoding="utf-8")
    code, out, err = run("export", "--root", str(tmp_path), "--format", "cff")  # no CITATION.cff, no config
    assert code == 0, err
    assert "  - alpha\n  - beta\n" in out
    (tmp_path / "CITATION.cff").write_text(out, encoding="utf-8")
    code, report, _ = run("check", "--root", str(tmp_path))
    assert code == 0, report


@pytest.mark.parametrize("fmt", ["cff", "zenodo"])
def test_export_keeps_every_author_when_npm_is_the_source(tmp_path: Path, run: "Run", fmt: str) -> None:
    (tmp_path / "package.json").write_text('{"name": "lensgrind", "version": "1.0.0"}', encoding="utf-8")
    people = [{"@type": "Person", "givenName": g, "familyName": f} for g, f in (("Tu", "Youyou"), ("Alan", "Turing"))]
    codemeta = {"@context": "https://w3id.org/codemeta/3.0", "name": "lensgrind", "author": people}
    (tmp_path / "codemeta.json").write_text(json.dumps(codemeta), encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('source = "package.json"\n', encoding="utf-8")
    code, out, err = run("export", "--root", str(tmp_path), "--format", fmt)
    assert code == 0, err
    assert "Turing" in out


def test_export_says_what_a_citation_file_leaves_out(tmp_path: Path, run: "Run") -> None:
    (tmp_path / "codemeta.json").write_text(
        json.dumps(
            {
                "@context": "https://w3id.org/codemeta/3.0",
                "name": "lensgrind",
                "author": [{"@type": "Person", "givenName": "Marie", "familyName": "Skłodowska-Curie"}],
                "license": "MIT AND Apache-2.0",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "citesync.toml").write_text('source = "codemeta.json"\n', encoding="utf-8")
    code, out, err = run("export", "--root", str(tmp_path), "--format", "cff")
    assert code == 0
    assert "title: lensgrind" in out
    assert "license" not in out
    assert err.startswith("leaving out license: ")


@pytest.mark.parametrize(
    ("fmt", "terms", "needs"),
    [
        ("cff", '"name": "x"', "no authors in codemeta.json, and CITATION.cff needs one"),
        (
            "codemeta",
            '"author": [{"@type": "Person", "name": "Ada Lovelace"}]',
            "no file gives a title, which the codemeta file needs",
        ),
    ],
)
def test_export_says_what_a_citation_file_needs(tmp_path: Path, run: "Run", fmt: str, terms: str, needs: str) -> None:
    (tmp_path / "codemeta.json").write_text(
        f'{{"@context": "https://w3id.org/codemeta/3.0", {terms}}}', encoding="utf-8"
    )
    (tmp_path / "citesync.toml").write_text('source = "codemeta.json"\n', encoding="utf-8")
    assert run("export", "--root", str(tmp_path), "--format", fmt) == (2, "", f"citesync: {needs}\n")


_FORMAT = {
    "citation.bib": "bibtex",
    "citation.csl.json": "csl-json",
    "citation.apa.txt": "apa",
    "schema.jsonld": "jsonld",
}


def test_bibtex_is_a_biblatex_software_entry_named_by_the_rows() -> None:
    from pybtex.database import parse_string  # noqa: PLC0415

    from citesync.mapping import load_mapping  # noqa: PLC0415

    rec = LENSGRIND | {"description": "Grinds lenses.", "swhid": "swh:1:dir:" + "0" * 40}
    bib = render("bibtex", rec)[0]
    assert bib.startswith("@software{lensgrind,\n")
    fields = parse_string(bib, "bibtex").entries["lensgrind"].fields
    mapping = load_mapping()
    for term in ("name", "version", "license", "identifier", "swhid", "codeRepository", "description", "keywords"):
        assert str(mapping["bibtex", term]) in fields, term
    assert (fields["date"], fields["year"]) == ("2026-10-31", "2026")  # biblatex reads date, plain BibTeX year
    assert fields["url"] == "https://example.org/lensgrind"  # plain BibTeX styles print url, not repository
    assert (fields["keywords"], fields["license"]) == ("optics, microscopy", "Apache-2.0")
    assert "note" not in fields

import base64
import io
import json
import tomllib
import zipfile
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from citesync.errors import CheckError
from citesync.playground import generate


def test_form_generates_matching_files():
    result = generate(
        {"details": {"title": "lensgrind", "authors": [{"given": "Marie", "family": "Skłodowska-Curie"}]}}
    )
    assert {"CITATION.cff", "codemeta.json"} <= result["files"].keys()
    assert json.loads(result["files"]["codemeta.json"])["author"][0]["familyName"] == "Skłodowska-Curie"
    assert result["review"] == []
    assert not any(f["severity"] == "error" for f in result["findings"])


def test_inferred_names_can_be_corrected():
    payload = {
        "filename": "package.json",
        "text": json.dumps({"name": "lensgrind", "author": "Antonie van Leeuwenhoek"}),
    }
    initial = generate(payload)
    assert initial["review"][0]["family"] == "Leeuwenhoek"
    result = generate({**payload, "names": [{"given": "Antonie", "family": "van Leeuwenhoek"}]})
    assert "family-names: van Leeuwenhoek" in result["files"]["CITATION.cff"]
    assert json.loads(result["files"]["codemeta.json"])["author"][0]["familyName"] == "van Leeuwenhoek"


@pytest.mark.parametrize("filename", ["../package.json", "/outside/package.json", "setup.py"])
def test_refuses_unrecognised_filenames(filename: str):
    with pytest.raises(CheckError, match="Choose"):
        generate({"filename": filename, "text": "{}"})


def test_invalid_input_is_not_silently_replaced():
    with pytest.raises(CheckError):
        generate({"filename": "pyproject.toml", "text": "[project\n"})


def test_preserves_source_extensions_and_role_objects():
    source = {
        "@context": "https://w3id.org/codemeta/3.0",
        "@type": "SoftwareSourceCode",
        "name": "lensgrind",
        "custom": {"keep": True},
        "author": [
            {
                "@type": "Person",
                "givenName": "Marie",
                "familyName": "Skłodowska-Curie",
                "@id": "https://orcid.org/0000-0002-1825-0097",
            },
            {
                "type": "Role",
                "schema:author": "https://orcid.org/0000-0002-1825-0097",
                "roleName": "https://credit.niso.org/contributor-roles/software/",
            },
        ],
    }
    result = generate({"filename": "codemeta.json", "text": json.dumps(source)})
    assert json.loads(result["files"]["codemeta.json"]) == source
    assert result["review"] == []


def test_zip_names_and_request_isolation():
    payload = {
        "filename": ".zenodo.json",
        "text": json.dumps({"title": "lensgrind", "creators": [{"name": "Skłodowska-Curie, Marie"}]}),
    }
    result = generate({**payload, "archive": True})
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(result["zip"]))) as archive:
        assert set(archive.namelist()) == set(result["files"])
        assert ".zenodo.json" in archive.namelist()
    with pytest.raises(CheckError):
        generate({"filename": "package.json", "text": '{"name":"empty"}'})


def test_orcid_alone_is_not_an_author_name():
    source = "cff-version: 1.2.0\ntitle: lensgrind\nauthors:\n  - orcid: https://orcid.org/0000-0002-1825-0097\n"
    with pytest.raises(CheckError, match="author"):
        generate({"filename": "CITATION.cff", "text": source})


def test_existing_cff_keeps_comments_and_line_endings():
    source = (
        "# Keep this note\n"
        "cff-version: 1.2.0\nmessage: Please cite this software.\ntitle: lensgrind\n"
        "authors:\n  - given-names: Marie\n    family-names: Skłodowska-Curie\n"
    ).replace("\n", "\r\n")
    result = generate({"filename": "CITATION.cff", "text": source})
    assert result["files"]["CITATION.cff"] == source
    assert result["review"] == []


def test_form_rejects_a_family_name_that_is_only_spaces():
    with pytest.raises(CheckError, match="family name"):
        generate({"details": {"title": "lensgrind", "authors": [{"given": "Marie", "family": "  "}]}})


def test_extra_exports_are_separated_from_incomplete_package_templates():
    result = generate(
        {
            "details": {
                "title": "lensgrind",
                "version": "1.4.0",
                "authors": [{"given": "Marie", "family": "Skłodowska-Curie"}],
            }
        }
    )
    assert {"citation.bib", "citation.csl.json"} <= result["files"].keys()
    assert set(result["templates"]) == {
        "pyproject.toml",
        "Cargo.toml",
        "package.json",
        "DESCRIPTION",
        "Project.toml",
        "typst.toml",
        "_extension.yml",
    }
    assert "zip" not in result
    assert "template_zip" not in result
    csl = json.loads(result["files"]["citation.csl.json"])
    assert csl[0]["type"] == "software"
    assert csl[0]["author"] == [{"family": "Skłodowska-Curie", "given": "Marie"}]
    assert "issued" not in csl[0]
    assert "@software{lensgrind," in result["files"]["citation.bib"]
    assert "{Skłodowska-Curie}, {Marie}" in result["files"]["citation.bib"]
    import tomllib  # noqa: PLC0415

    assert tomllib.loads(result["templates"]["pyproject.toml"])["project"]["name"] == "lensgrind"
    assert tomllib.loads(result["templates"]["Cargo.toml"])["package"]["version"] == "1.4.0"
    assert json.loads(result["templates"]["package.json"])["name"] == "lensgrind"


def test_editing_details_keeps_metadata_and_allows_a_partial_file_draft():
    source = {
        "@context": "https://w3id.org/codemeta/3.0",
        "@type": "SoftwareSourceCode",
        "name": "lensgrind",
        "author": [
            {
                "@type": "Person",
                "givenName": "Marie",
                "familyName": "Curie",
                "@id": "https://orcid.org/0000-0002-1825-0097",
                "affiliation": {"name": "Example Lab"},
            }
        ],
        "custom": {"keep": True},
        "keywords": ["optics"],
    }
    result = generate({"filename": "codemeta.json", "text": json.dumps(source), "edit": True})
    details = result["details"]
    assert details["title"] == "lensgrind"
    assert details["authors"][0]["family"] == "Curie"
    details["title"] = "lensgrind-next"
    details["authors"][0]["family"] = "Skłodowska-Curie"
    draft = json.loads(generate({"details": details, "draft": True})["draft"])
    assert draft["custom"] == {"keep": True}
    assert draft["keywords"] == ["optics"]
    assert draft["author"][0]["@id"] == source["author"][0]["@id"]
    assert draft["author"][0]["affiliation"] == {"name": "Example Lab"}
    assert draft["author"][0]["familyName"] == "Skłodowska-Curie"
    partial = generate(
        {"details": {"title": "draft only", "authors": [{"given": "Marie", "family": ""}]}, "draft": True}
    )
    assert json.loads(partial["draft"])["name"] == "draft only"


def test_zenodo_is_generated_in_the_playground():
    result = generate({"details": {"title": "lensgrind", "authors": [{"given": "Marie", "family": "Curie"}]}})
    assert ".zenodo.json" in result["files"]
    assert not any("requires an existing" in note for note in result["notes"])


def test_editing_details_keeps_organisations_and_credit_roles():
    source = {
        "@context": "https://w3id.org/codemeta/3.0",
        "name": "lensgrind",
        "author": [
            {"type": "Organization", "name": "Example Lab", "url": "https://example.org"},
            {
                "type": "Person",
                "givenName": "Marie",
                "familyName": "Curie",
                "id": "https://orcid.org/0000-0002-1825-0097",
            },
            {"type": "Role", "schema:author": "https://orcid.org/0000-0002-1825-0097", "roleName": "Software"},
        ],
    }
    details = generate({"filename": "codemeta.json", "text": json.dumps(source), "edit": True})["details"]
    assert details["authors"][0]["organization"] is True
    details["authors"][0]["family"] = "Example Optics Lab"
    changed = json.loads(generate({"details": details, "draft": True})["draft"])
    assert changed["author"][0]["@type"] == "Organization"
    assert changed["author"][0]["name"] == "Example Optics Lab"
    assert changed["author"][0]["url"] == "https://example.org"
    assert changed["author"][2] == source["author"][2]


def test_partial_file_drafts_obey_the_input_size_limit():
    with pytest.raises(CheckError, match="smaller than 1 MB"):
        generate({"details": {"document": {"custom": "x" * 1_000_001}}, "draft": True})


@given(
    st.dictionaries(
        st.text(max_size=20), st.one_of(st.none(), st.booleans(), st.integers(), st.text(max_size=30)), max_size=6
    )
)
@settings(max_examples=25)
def test_form_round_trip_retains_arbitrary_extra_codemeta_fields(extra: dict[str, str | int | bool | None]):
    source = {
        "@context": "https://w3id.org/codemeta/3.0",
        "name": "lensgrind",
        "author": [{"@type": "Person", "givenName": "Marie", "familyName": "Curie"}],
        "custom": extra,
    }
    details = generate({"filename": "codemeta.json", "text": json.dumps(source), "edit": True})["details"]
    details["title"] = "lensgrind-next"
    result = json.loads(generate({"details": details, "draft": True})["draft"])
    assert result["custom"] == extra
    assert result["name"] == "lensgrind-next"


@pytest.mark.parametrize(
    ("filename", "text"),
    [
        ("package.json", '{"name":"partial optics"}'),
        ("codemeta.json", '{"@context":"https://w3id.org/codemeta/3.0","name":"partial optics"}'),
    ],
)
def test_partial_files_can_open_in_the_details_form(filename: str, text: str):
    details = generate({"filename": filename, "text": text, "edit": True})["details"]
    assert details["title"] == "partial optics"
    assert details["authors"] == []


def test_r_and_julia_templates_read_back_through_the_imports(tmp_path: Path):
    from citesync.formats import Person, read_doc  # noqa: PLC0415
    from citesync.mapping import load_mapping  # noqa: PLC0415
    from citesync.playground_exports import package_templates  # noqa: PLC0415

    curie = Person(
        "Marie Skłodowska-Curie", "Marie", "Skłodowska-Curie", "0000-0002-1825-0097"
    )  # bare, as records hold it
    record = {
        "name": "lensgrind: Grind: Lenses",
        "version": "1.4.0",
        "description": "Measure\n  microscope optics.",
        "license": "GPL-3.0-or-later",
        "codeRepository": "https://github.com/example/lensgrind",
        "author": (
            curie,
            Person("Example Lab", organization=True),
            Person('Ant "Q" \\ Leeuwenhoek', 'Ant "Q" \\', "Leeuwenhoek"),
            Person("Tu", family="Tu"),
            Person(None, orcid="0000-0002-1825-0097"),
        ),
        "contributor": (Person("Tu Youyou", "Youyou", "Tu"),),
    }
    templates, notes = package_templates(record)
    for filename in ("DESCRIPTION", "Project.toml"):
        (tmp_path / filename).write_text(templates[filename])
    r = read_doc(tmp_path, "DESCRIPTION", load_mapping()).record
    assert (r["name"], r["version"], r["license"]) == ("lensgrind: Grind: Lenses", "1.4.0", "GPL-3.0-or-later")
    assert (r["description"], r["codeRepository"]) == (
        "Measure microscope optics.",
        "https://github.com/example/lensgrind",
    )
    assert [(p.given, p.family, p.orcid) for p in r["author"]] == [
        ("Marie", "Skłodowska-Curie", "0000-0002-1825-0097"),
        ("Example Lab", None, None),
        ('Ant "Q" \\', "Leeuwenhoek", None),
        (None, "Tu", None),
    ]
    assert [p.family for p in r["contributor"]] == ["Tu"]
    julia = read_doc(tmp_path, "Project.toml", load_mapping()).record
    assert julia["version"] == "1.4.0"
    assert 'orcid = "https://orcid.org/0000-0002-1825-0097"' in templates["Project.toml"]
    assert [(p.organization, p.family) for p in julia["author"]] == [
        (False, "Skłodowska-Curie"),
        (True, "Example Lab"),
        (False, "Leeuwenhoek"),
        (False, "Tu"),
    ]
    for note in (
        "DESCRIPTION: give the maintainer the role cre and an email, as CRAN asks.",
        "DESCRIPTION: check License against R's licence names; MIT and BSD add + file LICENSE.",
        "Project.toml: name omitted; a Julia package name is an identifier, such as Lensgrind.",
        "Project.toml: add the uuid Pkg generates for a new package.",
    ):
        assert note in notes


@pytest.mark.parametrize(
    ("spdx", "r"),
    [
        ("GPL-3.0-or-later", "GPL (>= 3)"),
        ("GPL-2.0-only", "GPL-2"),
        ("LGPL-2.1-or-later", "LGPL (>= 2.1)"),
        ("AGPL-3.0-only", "AGPL-3"),
        ("GPL-3.0-or-later OR MIT", "GPL (>= 3) | MIT"),
    ],
)
def test_the_r_template_spells_licences_as_r_does(spdx: str, r: str, tmp_path: Path):
    from citesync.formats import read_doc  # noqa: PLC0415
    from citesync.mapping import load_mapping  # noqa: PLC0415
    from citesync.playground_exports import package_templates  # noqa: PLC0415

    description = package_templates({"name": "lensgrind: Grind Lenses", "license": spdx})[0]["DESCRIPTION"]
    assert f"License: {r}\n" in description
    (tmp_path / "DESCRIPTION").write_text(description)
    assert read_doc(tmp_path, "DESCRIPTION", load_mapping()).record["license"] == spdx


def test_an_author_given_only_by_orcid_keeps_every_file():
    codemeta = {
        "@context": "https://w3id.org/codemeta/3.0",
        "name": "lensgrind",
        "author": [
            {"@type": "Person", "givenName": "Marie", "familyName": "Curie"},
            {"@id": "https://orcid.org/0000-0002-1825-0097"},
        ],
    }
    result = generate({"filename": "codemeta.json", "text": json.dumps(codemeta)})
    assert {"CITATION.cff", "DESCRIPTION", "Project.toml", "typst.toml", "_extension.yml"} <= result[
        "files"
    ].keys() | result["templates"].keys()


def test_typst_and_quarto_templates_carry_the_field_each_row_names_and_read_back(tmp_path: Path):
    import io  # noqa: PLC0415
    import tomllib  # noqa: PLC0415

    from ruamel.yaml import YAML  # noqa: PLC0415

    from citesync.formats import Person  # noqa: PLC0415
    from citesync.mapping import load_mapping, resolve  # noqa: PLC0415
    from citesync.playground_exports import package_templates  # noqa: PLC0415

    record = {
        "name": "lensgrind",
        "version": "1.4.0",
        "description": "Measure microscope optics.",
        "license": "Apache-2.0",
        "codeRepository": "https://github.com/example/lensgrind",
        "keywords": ("optics", "lens"),
        "author": (
            Person("Marie Skłodowska-Curie", "Marie", "Skłodowska-Curie", "0000-0002-1825-0097"),
            Person(None, orcid="0000-0002-1825-0097"),
            Person("Tu Youyou", "Youyou", "Tu"),
        ),
    }
    templates, notes = package_templates(record)
    rows = load_mapping()
    typst = tomllib.loads(templates["typst.toml"])
    quarto = YAML(typ="safe").load(io.StringIO(templates["_extension.yml"]))
    for fmt, doc, expected in (
        (
            "typst",
            typst,
            {
                "name": ["lensgrind"],
                "version": ["1.4.0"],
                "author": ["Marie Skłodowska-Curie", "Tu Youyou"],
                "license": ["Apache-2.0"],
                "description": ["Measure microscope optics."],
                "codeRepository": ["https://github.com/example/lensgrind"],
                "keywords": [["optics", "lens"]],
            },
        ),
        ("quarto", quarto, {"name": ["lensgrind"], "version": ["1.4.0"], "author": ["Marie Skłodowska-Curie"]}),
    ):
        for term, values in expected.items():
            path = rows[(fmt, term)]
            assert path is not None
            assert resolve(doc, path) == values, (fmt, term)
    assert "0000-0002" not in templates["typst.toml"] + templates["_extension.yml"]  # neither format has an ORCID
    assert set(quarto) == {"title", "version", "author"}
    assert "_extension.yml: only the first author is carried over; Quarto has one author string." in notes

    from citesync.formats import read_doc  # noqa: PLC0415

    for filename in ("typst.toml", "_extension.yml"):
        (tmp_path / filename).write_text(templates[filename], encoding="utf-8")
        doc = read_doc(tmp_path, filename, rows)
        assert doc.record["version"] == "1.4.0"
    assert [p.name for p in read_doc(tmp_path, "typst.toml", rows).record["author"]] == [
        "Marie Skłodowska-Curie",
        "Tu Youyou",
    ]


def test_the_typst_template_keeps_the_publishable_version_rule():
    from citesync.playground_exports import package_templates  # noqa: PLC0415

    leading_digit = package_templates({"name": "3d-plot", "version": "1.0.0"})[0]["typst.toml"]
    assert "name" not in tomllib.loads(leading_digit)["package"]
    assert "authors" not in leading_digit
    templates, notes = package_templates({"name": "Lens Grind", "version": "1.4.0-rc.1"})
    assert "version" not in templates["typst.toml"]
    assert "name" not in templates["typst.toml"]
    assert "typst.toml: version omitted: Typst package versions are major.minor.patch only, not 1.4.0-rc.1" in notes
    assert "typst.toml: name omitted; use lower-case letters, numbers and hyphens, such as lensgrind." in notes
    assert "title = " not in templates["typst.toml"]
    assert "title: Lens Grind\nversion: 1.4.0-rc.1\n" in templates["_extension.yml"]


def test_a_row_that_is_not_a_plain_key_path_stops_the_plugin_templates(monkeypatch: pytest.MonkeyPatch):
    from citesync import playground_exports  # noqa: PLC0415

    rows = dict(playground_exports.load_mapping())
    for broken, match in (({("typst", "name"): "a | b"}, "plain key path"), ({}, "no typst row for name")):
        patched = {k: v for k, v in rows.items() if k != ("typst", "name") or broken} | broken
        monkeypatch.setattr(playground_exports, "load_mapping", lambda patched=patched: patched)
        with pytest.raises(CheckError, match=match):
            playground_exports.package_templates({"name": "lensgrind"})

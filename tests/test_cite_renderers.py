"""Typed citations reuse the local serializers with their own resource kind."""

import json
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from citesync.config import Config
from citesync.errors import CheckError
from citesync.export import render
from citesync.formats import Doc, Person, codemeta_is_dataset
from citesync.mapping import load_mapping
from citesync.write import citation_file

RECORD = {
    "name": "Lensgrind calibration",
    "author": (Person("Tess Finch", "Tess", "Finch"),),
    "datePublished": "2025-09",
    "url": "https://example.org/record",
}


@pytest.mark.parametrize(
    ("kind", "bibtex_type", "ris_type", "csl_type"),
    [("article", "article", "JOUR", "article-journal"), ("dataset", "dataset", "DATA", "dataset")],
)
def test_cite_renderers_choose_the_resource_type(kind: str, bibtex_type: str, ris_type: str, csl_type: str) -> None:
    bibtex, _ = render("bibtex", RECORD, kind=kind)
    ris, _ = render("ris", RECORD, kind=kind)
    csl_json, _ = render("csl-json", RECORD, kind=kind)
    assert bibtex.startswith(f"@{bibtex_type}{{")
    assert f"  url = {{{RECORD['url']}}},\n" in bibtex
    assert ris.startswith(f"TY  - {ris_type}\n")
    assert f"UR  - {RECORD['url']}\n" in ris
    csl = json.loads(csl_json)[0]
    assert csl["type"] == csl_type
    assert csl["issued"] == {"date-parts": [[2025, 9]]}
    assert csl["URL"] == RECORD["url"]


def test_preprint_retains_versioned_identifier() -> None:
    record = RECORD | {"arxiv": "2509.12345v2", "primaryCategory": "cs.DL"}
    bibtex, _ = render("bibtex", record, kind="preprint")
    ris, _ = render("ris", record, kind="preprint")
    csl_json, _ = render("csl-json", record, kind="preprint")
    assert "  eprint = {2509.12345v2}," in bibtex
    assert "  archivePrefix = {arXiv}," in bibtex
    assert "  primaryClass = {cs.DL}," in bibtex
    assert "N1  - arXiv:2509.12345v2" in ris
    assert json.loads(csl_json)[0]["genre"] == "Preprint"


def test_article_retains_journal_details() -> None:
    record = RECORD | {"containerTitle": "Journal of Calibration", "volume": "2", "issue": "3", "pages": "4\u20139"}
    bibtex, _ = render("bibtex", record, kind="article")
    ris, _ = render("ris", record, kind="article")
    csl_json, _ = render("csl-json", record, kind="article")
    assert "  journal = {Journal of Calibration}," in bibtex
    assert "  pages = {4\u20139}," in bibtex
    assert "JF  - Journal of Calibration" in ris
    assert "SP  - 4\nEP  - 9" in ris
    assert json.loads(csl_json)[0]["container-title"] == "Journal of Calibration"


def test_conference_paper_retains_proceedings_venue() -> None:
    record = RECORD | {"containerTitle": "Calibration Methods Proceedings"}
    bibtex, _ = render("bibtex", record, kind="conference")
    ris, _ = render("ris", record, kind="conference")
    csl_json, _ = render("csl-json", record, kind="conference")
    assert bibtex.startswith("@inproceedings{")
    assert "  booktitle = {Calibration Methods Proceedings}," in bibtex
    assert ris.startswith("TY  - CPAPER\n")
    assert "T2  - Calibration Methods Proceedings" in ris
    csl = json.loads(csl_json)[0]
    assert csl["type"] == "paper-conference"
    assert csl["container-title"] == "Calibration Methods Proceedings"


def test_dataset_citation_files_set_type_and_preserve_date_precision(tmp_path: Path) -> None:
    source = Doc("remote.json", "codemeta", RECORD, frozenset(), None, release=True)
    mapping = load_mapping()
    cff, notes = citation_file("cff", tmp_path, Config(), source, mapping, resource_type="dataset")
    codemeta, codemeta_notes = citation_file("codemeta", tmp_path, Config(), source, mapping, resource_type="dataset")
    assert YAML(typ="safe").load(cff)["type"] == "dataset"
    assert "date-released" not in cff
    assert "datePublished" in notes
    data = json.loads(codemeta)
    assert data["@type"] == "https://schema.org/Dataset"
    assert codemeta_is_dataset(data)
    assert "datePublished" not in data
    assert "datePublished" in codemeta_notes


def test_software_only_format_refuses_an_article() -> None:
    with pytest.raises(CheckError, match=r"apa.*article"):
        render("apa", RECORD, kind="article")


@pytest.mark.parametrize(("fmt", "kind"), [("cff", "article"), ("zenodo", "dataset")])
def test_citation_file_rejects_incompatible_type(fmt: str, kind: str, tmp_path: Path) -> None:
    source = Doc("remote.json", "codemeta", RECORD, frozenset(), None, release=True)
    with pytest.raises(CheckError, match=rf"{fmt} does not support resource type '{kind}'"):
        citation_file(fmt, tmp_path, Config(), source, load_mapping(), resource_type=kind)

import hashlib
import json
import unicodedata
from pathlib import Path

import pytest

from citesync import codecs
from citesync.cli import main
from citesync.formats import Person, read_doc, same_name
from citesync.mapping import load_mapping

FIXTURE = Path(__file__).parent / "contracts/shared-names"
CORPUS = json.loads((FIXTURE / "people-v1.json").read_text(encoding="utf-8"))


def test_canonical_corpus_pin():
    data = (FIXTURE / "people-v1.json").read_bytes()
    source = json.loads((FIXTURE / "SOURCE.json").read_text(encoding="utf-8"))
    assert CORPUS["version"] == 1
    assert source["source_revision_kind"] == "git-blob"
    assert source["source_path"] == "conformance/names/people-v1.json"
    assert source["license"] == "MIT"
    assert (FIXTURE / source["license_file"]).is_file()
    assert hashlib.sha256(data).hexdigest() == source["sha256"]
    assert hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == source["source_revision"]  # noqa: S324 - Git's content identifier, not a security digest.


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["id"])
def test_structured_names_and_cff_fold(tmp_path: Path, case: dict):
    if case["id"] == "nfd":
        assert case["display"] != unicodedata.normalize("NFC", case["display"])
    expected = case["codemeta"]
    given, family = expected["givenName"], expected["familyName"]
    cff = "cff-version: 1.2.0\nmessage: Test metadata\ntitle: Example Lab\nauthors: " + json.dumps([case["cff"]]) + "\n"
    (tmp_path / "CITATION.cff").write_text(cff, encoding="utf-8")
    codemeta = {"@context": "https://w3id.org/codemeta/3.0", "author": [expected]}
    (tmp_path / "codemeta.json").write_text(json.dumps(codemeta), encoding="utf-8")
    expected_person = Person(f"{given} {family}", given, family)
    cff_family = " ".join(
        case["cff"][key] for key in ("name-particle", "family-names", "name-suffix") if case["cff"].get(key)
    )
    cff_person = read_doc(tmp_path, "CITATION.cff", load_mapping()).record["author"][0]
    assert cff_person == Person(f"{case['cff']['given-names']} {cff_family}", case["cff"]["given-names"], cff_family)
    assert same_name(cff_person, expected_person)
    assert read_doc(tmp_path, "codemeta.json", load_mapping()).record["author"] == (expected_person,)
    if "zenodo_name" in case:
        (tmp_path / ".zenodo.json").write_text(
            json.dumps({"creators": [{"name": case["zenodo_name"]}]}), encoding="utf-8"
        )
        assert read_doc(tmp_path, ".zenodo.json", load_mapping()).record["author"] == (expected_person,)
    assert not same_name(expected_person, Person(f"{family} {given}", family, given))
    for display in case["equivalent_names"]:
        assert same_name(expected_person, Person(display))
        assert same_name(Person(display), expected_person)


@pytest.mark.parametrize("case", CORPUS["orcid_cases"])
def test_orcid_normalization_is_not_checksum_validation(case: dict):
    assert codecs.orcid_decode(case["input"]) == case["normalized"]


@pytest.mark.parametrize("case", CORPUS["cases"], ids=lambda case: case["id"])
def test_write_preserves_structured_parts(tmp_path: Path, case: dict):
    cff = "cff-version: 1.2.0\nmessage: Test metadata\ntitle: Example Lab\nauthors: " + json.dumps([case["cff"]]) + "\n"
    (tmp_path / "CITATION.cff").write_text(cff, encoding="utf-8")
    target = tmp_path / "codemeta.json"
    target.write_text(
        json.dumps(
            {
                "@context": "https://w3id.org/codemeta/3.0",
                "author": [{"givenName": "Rosalind", "familyName": "Franklin"}],
            }
        ),
        encoding="utf-8",
    )
    assert main(["write", "--root", str(tmp_path), "--source", "CITATION.cff"]) == 0
    person = json.loads(target.read_text(encoding="utf-8"))["author"][0]
    assert person["@type"] == "Person"
    assert {key: unicodedata.normalize("NFC", person[key]) for key in case["codemeta"]} == case["codemeta"]
    if case["id"] == "nfd":
        assert person["familyName"] == case["cff"]["family-names"]
    before = target.read_bytes()
    assert main(["write", "--root", str(tmp_path), "--source", "CITATION.cff"]) == 0
    assert target.read_bytes() == before

"""Maven citation fields come from the pinned mapping and the named POM alone."""

import json
from pathlib import Path
from string import ascii_letters
from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st
from ruamel.yaml import YAML

from citesync.check import check
from citesync.config import Config
from citesync.errors import UnreadableError
from citesync.formats import read_doc
from citesync.mapping import load_mapping, resolve
from citesync.maven import parse
from citesync.playground import generate
from citesync.write import write

if TYPE_CHECKING:
    from tests.conftest import Run

POM = """<project xmlns="http://maven.apache.org/POM/4.0.0">
  <modelVersion>4.0.0</modelVersion>
  <parent><version>2.3.4</version><relativePath>../parent/pom.xml</relativePath></parent>
  <artifactId>optics</artifactId>
  <name>Lensgrind</name>
  <description>Measure microscope optics.</description>
  <developers>
    <developer><name>Ada Example</name></developer>
    <developer><name>Mira Example</name></developer>
  </developers>
  <contributors><contributor><name>Grace Example</name></contributor></contributors>
  <licenses><license><url>https://spdx.org/licenses/MIT</url></license></licenses>
  <scm><url>https://example.org/lensgrind</url></scm>
</project>
"""


def test_maven_cli_and_playground(tmp_path: Path, run: "Run"):
    path = tmp_path / "pom.xml"
    path.write_bytes(POM.replace("\n", "\r\n").encode())
    original = path.read_bytes()
    code, out, err = run("init", "--source", "pom.xml", "--root", str(tmp_path))
    assert (code, err) == (0, ""), out
    cff = YAML(typ="safe").load(tmp_path / "CITATION.cff")
    assert cff["title"] == "Lensgrind"
    assert cff["version"] == "2.3.4"
    assert cff["repository-code"] == "https://example.org/lensgrind"
    assert cff["license"] == "MIT"
    assert [author["given-names"] for author in cff["authors"]] == ["Ada", "Mira"]
    citation = tmp_path / "CITATION.cff"
    citation.write_text(citation.read_text(encoding="utf-8").replace("2.3.4", "1.0.0"), encoding="utf-8")
    config = Config(manifests=("pom.xml",), write_manifests=("version", "author"))
    [finding] = [
        finding for finding in check(tmp_path, config)[0] if finding.file == path.name and finding.term == "version"
    ]
    assert (finding.line, finding.column) == (3, 11)
    assert path.name not in write(tmp_path, config)[0]
    assert path.read_bytes() == original
    result = generate({"filename": path.name, "text": POM})
    codemeta = json.loads(result["files"]["codemeta.json"])
    assert codemeta["contributor"][0]["givenName"] == "Grace"


@pytest.mark.parametrize(
    ("text", "diagnostic"),
    [
        ("<project><name>Example</project>", "mismatched tag"),
        ("<!DOCTYPE project><project/>", "document type"),
        ("<project xmlns='urn:other'/>", "Maven project"),
    ],
)
def test_maven_rejects_invalid_xml(tmp_path: Path, text: str, diagnostic: str):
    (tmp_path / "pom.xml").write_text(text, encoding="utf-8")
    with pytest.raises(UnreadableError, match=diagnostic):
        read_doc(tmp_path, "pom.xml", load_mapping())


@pytest.mark.parametrize(("version", "expected"), [("1.2.3", "1.2.3"), ("${revision}", None)])
def test_project_version_overrides_parent_without_interpolation(tmp_path: Path, version: str, expected: str | None):
    (tmp_path / "pom.xml").write_text(POM.replace("<artifactId>", f"<version>{version}</version><artifactId>"))
    record = read_doc(tmp_path, "pom.xml", load_mapping()).record
    assert record.get("version") == expected


def test_multiple_maven_licence_urls_remain_in_codemeta(tmp_path: Path, run: "Run"):
    text = POM.replace(
        "</licenses>",
        "<license><url>https://example.org/CustomLicence</url></license></licenses>",
    )
    (tmp_path / "pom.xml").write_text(text, encoding="utf-8")
    (tmp_path / ".zenodo.json").write_text("{}", encoding="utf-8")
    code, output, err = run("init", "--source", "pom.xml", "--root", str(tmp_path))
    assert (code, err) == (0, ""), output
    assert "cff-1.2.0 needs a specific licence" in output
    cff = YAML(typ="safe").load(tmp_path / "CITATION.cff")
    assert "license" not in cff
    assert "license-url" not in cff
    generated = generate({"filename": "pom.xml", "text": text})
    assert json.loads(generated["files"]["codemeta.json"])["license"] == [
        "https://spdx.org/licenses/MIT",
        "https://example.org/CustomLicence",
    ]


@given(st.lists(st.text(alphabet=ascii_letters, min_size=1, max_size=20), max_size=5))
def test_maven_projected_developers_keep_their_order(names: list[str]):
    mapping = load_mapping()
    developers = "".join(f"<developer><name>{name}</name></developer>" for name in names)
    text = f"<project><developers>{developers}</developers></project>"
    assert resolve(parse(text, "pom.xml", mapping), str(mapping["maven", "author.givenName"])) == names


@pytest.mark.parametrize(
    "url", ["LICENSE.txt", "file:///example/COPYING", "${project.url}/LICENSE", "https:///License"]
)
def test_maven_licence_links_are_never_guessed_as_spdx_ids(url: str):
    result = generate({"filename": "pom.xml", "text": POM.replace("https://spdx.org/licenses/MIT", url)})
    cff = YAML(typ="safe").load(result["files"]["CITATION.cff"])
    assert "license" not in cff
    assert "license-url" not in cff
    assert "license" not in json.loads(result["files"]["codemeta.json"])


def test_maven_preserves_a_valid_licence_url_with_an_uppercase_scheme():
    url = "HTTPS://example.org/License"
    result = generate({"filename": "pom.xml", "text": POM.replace("https://spdx.org/licenses/MIT", url)})
    assert YAML(typ="safe").load(result["files"]["CITATION.cff"])["license-url"] == url


@pytest.mark.parametrize("scheme", ["ftp", "sftp"])
def test_maven_checks_licence_url_path_case(tmp_path: Path, run: "Run", scheme: str):
    url = f"{scheme}://example.org/License"
    (tmp_path / "pom.xml").write_text(POM.replace("https://spdx.org/licenses/MIT", url), encoding="utf-8")
    code, output, err = run("init", "--source", "pom.xml", "--root", str(tmp_path))
    assert (code, err) == (0, ""), output
    citation = tmp_path / "CITATION.cff"
    citation.write_text(citation.read_text(encoding="utf-8").replace("/License", "/license"), encoding="utf-8")
    findings, _, _ = check(tmp_path, Config(manifests=("pom.xml",)))
    assert any(f.file == "pom.xml" and f.term == "license" for f in findings)

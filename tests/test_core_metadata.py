"""Distribution metadata is a read-only source, without a package build or import."""

import json
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from citesync.check import check
from citesync.config import Config
from citesync.errors import UnreadableError
from citesync.formats import load, read_doc
from citesync.mapping import load_mapping
from citesync.playground import generate
from citesync.write import write

if TYPE_CHECKING:
    from tests.conftest import Run

METADATA = """Metadata-Version: 2.6
Name: lensgrind
Version: 1.4.0
Summary: Measure microscope optics.
Author: Marie Skłodowska-Curie
Author: Antonie van Leeuwenhoek
Author-email: Marie Skłodowska-Curie <marie@example.org>
License-Expression: Apache-2.0
Project-URL: Documentation, https://example.org/docs
Project-URL: Repository, https://example.org/lensgrind
Keywords: optics,microscopy

Long description, not executable code.
"""


@pytest.mark.parametrize("filename", ["PKG-INFO", "METADATA"])
def test_distribution_source_generates_all_citation_files(filename: str, tmp_path: Path, run: "Run") -> None:
    source = tmp_path / filename
    source.write_bytes(METADATA.replace("\n", "\r\n").encode())
    before = source.read_bytes()
    code, out, err = run("init", "--source", filename, "--root", str(tmp_path))
    assert (code, err) == (0, ""), out
    config = Config(
        source=filename, files=("codemeta.json", ".zenodo.json"), manifests=(), write_manifests=("version",)
    )
    write(tmp_path, config)
    data = json.loads((tmp_path / "codemeta.json").read_text())
    assert data["name"] == "lensgrind"
    assert data["license"] == "https://spdx.org/licenses/Apache-2.0"
    assert data["codeRepository"] == "https://example.org/lensgrind"
    assert len(data["author"]) == 2
    assert source.read_bytes() == before
    assert write(tmp_path, config)[0] == {}
    result = generate({"filename": filename, "text": METADATA})
    assert ".zenodo.json" in result["files"]
    assert "Skłodowska-Curie" in result["files"]["CITATION.cff"]


def test_legacy_licence_is_not_invented_as_spdx(tmp_path: Path) -> None:
    source = tmp_path / "PKG-INFO"
    source.write_text(METADATA.replace("License-Expression: Apache-2.0", "License: A custom licence"))
    doc = read_doc(tmp_path, "PKG-INFO", load_mapping())
    assert "license" not in doc.record
    assert any("License" in message for _, message in doc.import_notes)


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("Name: lensgrind\n", ""),
        lambda s: s.replace("Version: 1.4.0\n", ""),
        lambda s: s.replace("Metadata-Version: 2.6", "Metadata-Version: 3.0"),
        lambda s: s.replace("Name: lensgrind", "Name: lensgrind\nName: other"),
        lambda s: s.replace(
            "Project-URL: Documentation, https://example.org/docs", "Project-URL: Repository, https://example.org/other"
        ),
        lambda s: s.replace("License-Expression: Apache-2.0", "License-Expression: invented licence"),
        lambda s: s.replace("Summary:", "broken line\nSummary:"),
    ],
)
def test_malformed_or_ambiguous_metadata_is_actionable(change: Callable[[str], str], tmp_path: Path) -> None:
    path = tmp_path / "METADATA"
    path.write_text(change(METADATA))
    with pytest.raises(UnreadableError):
        read_doc(tmp_path, "METADATA", load_mapping())


def test_repeated_urls_and_named_contacts_are_retained_by_adapter(tmp_path: Path) -> None:
    path = tmp_path / "METADATA"
    path.write_text(METADATA)
    data = load(path, "METADATA")["project"]
    assert data["urls"] == {"Source": "https://example.org/lensgrind"}
    assert data["authors"] == [
        {"name": "Marie Skłodowska-Curie", "email": "marie@example.org"},
        {"name": "Antonie van Leeuwenhoek"},
    ]


@given(st.text(alphabet=st.characters(categories=("L",)), min_size=1, max_size=40))
def test_unicode_author_names_survive_import(name: str) -> None:
    payload = METADATA.replace("Marie Skłodowska-Curie", name).replace("Author: Antonie van Leeuwenhoek\n", "")
    result = generate({"filename": "METADATA", "text": payload})
    people = json.loads(result["files"]["codemeta.json"])["author"]
    joined = " ".join(part for person in people for part in (person.get("givenName"), person.get("familyName")) if part)
    assert joined == unicodedata.normalize("NFC", name)


def test_author_order_survives_contact_enrichment(tmp_path: Path) -> None:
    path = tmp_path / "METADATA"
    path.write_text(
        METADATA.replace(
            "Author: Marie Skłodowska-Curie\nAuthor: Antonie van Leeuwenhoek",
            "Author: Antonie van Leeuwenhoek\nAuthor: Marie Skłodowska-Curie",
        )
    )
    people = load(path, "METADATA")["project"]["authors"]
    assert [person["name"] for person in people] == ["Antonie van Leeuwenhoek", "Marie Skłodowska-Curie"]


def test_distribution_metadata_is_never_a_write_target(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(
        "cff-version: 1.2.0\nmessage: Cite this.\ntitle: lensgrind\nversion: 2.0.0\n"
    )
    path = tmp_path / "METADATA"
    path.write_text(METADATA)
    original = path.read_bytes()
    config = Config(manifests=("METADATA",), write_manifests=("version",))
    changed, _, _, _ = write(tmp_path, config)
    assert "METADATA" not in changed
    assert path.read_bytes() == original


def test_private_licence_reference_does_not_become_a_public_spdx_url(tmp_path: Path) -> None:
    path = tmp_path / "METADATA"
    path.write_text(METADATA.replace("Apache-2.0", "LicenseRef-Example-Lab"))
    doc = read_doc(tmp_path, "METADATA", load_mapping())
    assert "license" not in doc.record
    assert any("LicenseRef" in message for _, message in doc.import_notes)


def test_import_notices_are_reported_by_check(tmp_path: Path) -> None:
    path = tmp_path / "METADATA"
    path.write_text(METADATA.replace("License-Expression: Apache-2.0", "License: Custom lab terms"))
    found, _, _ = check(tmp_path, Config(source="METADATA", manifests=()))
    notices = [f for f in found if f.rule == "metadata-omitted"]
    assert len(notices) == 1
    assert (notices[0].file, notices[0].term, notices[0].severity) == ("METADATA", "license", "warning")
    assert "License" in notices[0].message


def test_read_only_source_does_not_stop_updates_to_other_files(tmp_path: Path) -> None:
    (tmp_path / "METADATA").write_text(METADATA)
    (tmp_path / "CITATION.cff").write_text(
        "cff-version: 1.2.0\nmessage: Cite this.\ntitle: lensgrind\nversion: 2.0.0\n"
    )
    changed, _, _, _ = write(tmp_path, Config(source="METADATA", manifests=()))
    assert "version: 1.4.0" in changed["CITATION.cff"]
    assert "METADATA" not in changed


def test_legacy_sdist_metadata_does_not_promote_maintainers(tmp_path: Path) -> None:
    path = tmp_path / "PKG-INFO"
    path.write_text(
        "Metadata-Version: 1.2\nName: lensgrind\nVersion: 1.0\nAuthor: Antonie van Leeuwenhoek\n"
        "Author-email: antonie@example.org\n"
        "Maintainer: Marie Skłodowska-Curie\n"
        "Maintainer-email: marie@example.org\nLicense: MIT\n"
    )
    doc = read_doc(tmp_path, "PKG-INFO", load_mapping())
    assert doc.record["license"] == "MIT"
    assert [person.name for person in doc.record["author"]] == ["Antonie van Leeuwenhoek"]
    assert "contributor" not in doc.record


def test_wheel_metadata_can_use_only_named_email_authors(tmp_path: Path) -> None:
    path = tmp_path / "METADATA"
    path.write_text(
        "Metadata-Version: 2.6\nName: lensgrind\nVersion: 1.0\n"
        "Author-email: Marie Skłodowska-Curie <marie@example.org>\n\nMeasure optics.\n"
    )
    doc = read_doc(tmp_path, "METADATA", load_mapping())
    assert [person.name for person in doc.record["author"]] == ["Marie Skłodowska-Curie"]
    assert "description" not in doc.record  # the body is the README, not a Summary


def test_missing_optional_distribution_fields_stay_absent(tmp_path: Path) -> None:
    path = tmp_path / "METADATA"
    path.write_text("Metadata-Version: 2.6\nName: lensgrind\nVersion: 1.0\n")
    assert read_doc(tmp_path, "METADATA", load_mapping()).record == {"name": "lensgrind", "version": "1.0"}


BARE = "Metadata-Version: 2.6\nName: lensgrind\nVersion: 1.0\n"


@pytest.mark.parametrize(
    ("headers", "repository"),
    [
        ("Project-URL: Source Code, https://example.org/a\n", "https://example.org/a"),
        ("Project-URL: source, https://example.org/a\n", "https://example.org/a"),
        ("Project-URL: GitHub, https://example.org/a\n", "https://example.org/a"),
        ("Project-URL: Source-Code, https://example.org/a\n", "https://example.org/a"),
        (
            "Project-URL: GitHub, https://example.org/b\nProject-URL: Repository, https://example.org/a\n",
            "https://example.org/a",
        ),
        (
            "Project-URL: Repository, https://example.org/b\nProject-URL: Source, https://example.org/a\n",
            "https://example.org/a",
        ),
        ("Home-page: https://example.org/home\nProject-URL: Source, https://example.org/a\n", "https://example.org/a"),
        ("Home-page: https://example.org/home\n", "https://example.org/home"),
        (
            "Project-URL: Source Code, https://example.org/b\nProject-URL: Repository, https://example.org/a\n",
            "https://example.org/a",
        ),
        ("Project-URL: Documentation, https://example.org/docs\n", None),
    ],
)
def test_repository_comes_from_the_well_known_labels_in_order(
    headers: str, repository: str | None, tmp_path: Path
) -> None:
    (tmp_path / "METADATA").write_text(BARE + headers)
    assert read_doc(tmp_path, "METADATA", load_mapping()).record.get("codeRepository") == repository


def test_description_comes_from_summary_only(tmp_path: Path) -> None:
    (tmp_path / "METADATA").write_text(BARE + "Description: The whole README.\n\nBody text.\n")
    assert "description" not in read_doc(tmp_path, "METADATA", load_mapping()).record


def test_labels_that_normalise_alike_must_agree(tmp_path: Path) -> None:
    (tmp_path / "METADATA").write_text(
        BARE + "Project-URL: Source Code, https://example.org/a\nProject-URL: source-code, https://example.org/b\n"
    )
    with pytest.raises(UnreadableError, match="conflicting values"):
        read_doc(tmp_path, "METADATA", load_mapping())

"""A hand-checked contribution record at the installed CLI boundary."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import example, given
from hypothesis import strategies as st
from ruamel.yaml import YAML

from citesync.formats import codemeta_orcid, dangling_roles

if TYPE_CHECKING:
    from tests.conftest import Run

CONTRACT = Path(__file__).parent / "contracts" / "contributions"
FILES = ("codemeta.json", "CITATION.cff", ".zenodo.json", "citesync.toml")


@pytest.fixture
def contribution_repo(tmp_path: Path) -> Path:
    for name in FILES:
        shutil.copyfile(CONTRACT / name, tmp_path / name)
    return tmp_path


def cli(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and test-owned CLI arguments
        [sys.executable, "-m", "citesync", *args, "--root", str(root), "--format", "json"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )


def snapshot(root: Path) -> dict[str, bytes]:
    return {name: (root / name).read_bytes() for name in FILES}


def test_contribution_contract_writes_hand_checked_people_and_is_idempotent(contribution_repo: Path) -> None:
    root = contribution_repo
    original = (root / "codemeta.json").read_bytes()
    expected = json.loads((CONTRACT / "expected.json").read_text(encoding="utf-8"))
    result = cli(root, "write")
    assert result.returncode == 0, result.stdout + result.stderr
    cff = YAML(typ="safe").load((root / "CITATION.cff").read_text(encoding="utf-8"))
    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    assert cff["authors"] == expected["cff_authors"]
    assert zenodo["creators"] == expected["zenodo_creators"]
    assert zenodo["contributors"] == expected["zenodo_contributors"]
    assert (root / "codemeta.json").read_bytes() == original
    assert "contributors" not in cff
    checked = cli(root, "check")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert not [f for f in json.loads(checked.stdout)["findings"] if f["severity"] != "info"]
    after = snapshot(root)
    assert cli(root, "write").returncode == 0
    assert snapshot(root) == after


@pytest.mark.parametrize(
    "role_name",
    ["https://credit.niso.org/contributor-roles/software/", "https://example.org/roles/microscopy"],
)
def test_editing_codemeta_preserves_the_role_graph(contribution_repo: Path, role_name: str) -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    path = root / "codemeta.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    source["author"][-1]["roleName"] = role_name
    path.write_text(json.dumps(source, ensure_ascii=False) + "\n", encoding="utf-8")
    config = root / "citesync.toml"
    config.write_text('source = "CITATION.cff"\nmanifests = []\n', encoding="utf-8")
    cff = root / "CITATION.cff"
    cff.write_text(cff.read_text(encoding="utf-8").replace("1.0.0", "1.0.1"), encoding="utf-8")
    result = cli(root, "write")
    assert result.returncode == 0, result.stdout + result.stderr
    expected = {**source, "version": "1.0.1"}
    assert json.loads(path.read_text(encoding="utf-8")) == expected


def test_a_new_zenodo_contributor_without_a_chosen_type_is_an_explicit_gap(contribution_repo: Path) -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    path = root / ".zenodo.json"
    zenodo = json.loads(path.read_text(encoding="utf-8"))
    zenodo["contributors"] = [{"name": "Curie, Pierre", "type": "Other"}]
    path.write_text(json.dumps(zenodo, ensure_ascii=False) + "\n", encoding="utf-8")
    before = snapshot(root)
    result = cli(root, "write")
    assert result.returncode == 1
    assert "Zenodo needs a type" in result.stdout
    assert snapshot(root) == before


def test_a_role_without_a_linked_person_warns_without_inventing_identity(contribution_repo: Path) -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    path = root / "codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["author"][0]["id"]
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    before = snapshot(root)
    result = cli(root, "check")
    assert result.returncode == 0, result.stdout + result.stderr
    warnings = [f for f in json.loads(result.stdout)["findings"] if f["severity"] == "warning"]
    assert [(f["rule"], f["file"], f["term"]) for f in warnings] == [("role-dangling", "codemeta.json", "author")]
    assert snapshot(root) == before


def test_updating_an_existing_person_id_keeps_the_alias_spelling(contribution_repo: Path, run: "Run") -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    config = root / "citesync.toml"
    config.write_text('source = "CITATION.cff"\nmanifests = []\n', encoding="utf-8")
    path = root / "codemeta.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    # An invalid old iD exercises correction without using another person's identifier.
    source["author"][0]["id"] = "https://orcid.org/0000-0000-0000-0000"
    path.write_text(json.dumps(source, ensure_ascii=False) + "\n", encoding="utf-8")
    code, out, err = run("write", "--root", str(root))
    assert (code, err) == (0, ""), out
    person = json.loads(path.read_text(encoding="utf-8"))["author"][0]
    assert person == {**source["author"][0], "id": "https://orcid.org/0000-0002-1825-0097"}


def test_removing_a_person_with_aliases_preserves_roles_and_reports_the_dangling_link(
    contribution_repo: Path, run: "Run"
) -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    config = root / "citesync.toml"
    config.write_text('source = "CITATION.cff"\nfiles = ["codemeta.json"]\nmanifests = []\n', encoding="utf-8")
    cff = root / "CITATION.cff"
    yaml = YAML()
    data = yaml.load(cff.read_text(encoding="utf-8"))
    del data["authors"][0]
    with cff.open("w", encoding="utf-8") as stream:
        yaml.dump(data, stream)
    path = root / "codemeta.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    code, out, err = run("write", "--root", str(root))
    assert (code, err) == (0, ""), out
    assert json.loads(path.read_text(encoding="utf-8")) == {**original, "author": original["author"][1:]}
    assert "role-dangling" in out


def test_a_non_codemeta_id_stays_metadata_when_correcting_an_orcid(contribution_repo: Path, run: "Run") -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    path = root / ".zenodo.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    original["creators"][0].update(orcid="0000-0000-0000-0000", id="https://example.org/people/microscopist")
    path.write_text(json.dumps(original, ensure_ascii=False) + "\n", encoding="utf-8")
    code, out, err = run("write", "--root", str(root))
    assert (code, err) == (0, ""), out
    original["creators"][0]["orcid"] = "0000-0002-1825-0097"
    assert json.loads(path.read_text(encoding="utf-8")) == original


@pytest.mark.parametrize("key", ["id", "@id"])
@pytest.mark.parametrize("identifier", ["https://example.org/people/microscopist", "#microscopist", "_:microscopist"])
def test_other_codemeta_identifiers_never_replace_orcids(contribution_repo: Path, key: str, identifier: str) -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    path = root / "codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["author"][0].pop("id")
    data["author"][0][key] = identifier
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    before = snapshot(root)
    result = cli(root, "write")
    assert result.returncode == 0, result.stdout + result.stderr
    assert snapshot(root) == before


@pytest.mark.parametrize("key", ["id", "@id"])
def test_other_codemeta_identifiers_survive_target_updates_and_block_removal(
    contribution_repo: Path, key: str, run: "Run"
) -> None:
    root = contribution_repo
    assert cli(root, "write").returncode == 0
    (root / "citesync.toml").write_text(
        'source = "CITATION.cff"\nfiles = ["codemeta.json"]\nmanifests = []\n', encoding="utf-8"
    )
    path = root / "codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["author"][0].pop("id")
    data["author"][0][key] = "https://example.org/people/microscopist"
    path.write_text(json.dumps(data, ensure_ascii=False) + "\n", encoding="utf-8")
    cff = root / "CITATION.cff"
    yaml = YAML()
    source = yaml.load(cff.read_text(encoding="utf-8"))
    source["version"] = "1.0.1"
    with cff.open("w", encoding="utf-8") as stream:
        yaml.dump(source, stream)
    code, out, err = run("write", "--root", str(root))
    assert (code, err) == (0, ""), out
    assert json.loads(path.read_text(encoding="utf-8")) == {**data, "version": "1.0.1"}
    del source["authors"][0]
    with cff.open("w", encoding="utf-8") as stream:
        yaml.dump(source, stream)
    before = snapshot(root)
    code, out, err = run("write", "--root", str(root))
    assert (code, err) == (1, ""), out
    assert f"drop the {key}" in out
    assert snapshot(root) == before


@given(st.text())
@example("https://orcid.org/0000-0002-1825-0097")
@example("http://www.orcid.org/0000-0002-1825-009x/")
@example("https://example.org/people/microscopist")
def test_codemeta_orcid_decoding_is_idempotent(raw: str) -> None:
    once = codemeta_orcid(raw)
    assert codemeta_orcid(once) == once


@pytest.mark.parametrize("identifier", ["https://example.org/people/microscopist", "#microscopist", "_:microscopist"])
def test_role_links_without_orcids_are_not_reported_as_dangling_orcids(identifier: str) -> None:
    assert dangling_roles({"author": [{"type": "Role", "schema:author": {"id": identifier}}]}) == ()

"""Run the installed Matrix CLI and carry its attribution through the installed citesync CLI."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from tests.test_contribution_contract import CONTRACT, FILES, cli, snapshot


@pytest.fixture
def matrix_repo(tmp_path: Path) -> Path:
    package = Path(__file__).resolve().parents[1] / "node_modules/credit-matrix"
    if not package.exists():
        pytest.skip("Run pnpm install to enable the Matrix integration tests")
    producer = package / "dist/cli.js"
    result = subprocess.run(  # noqa: S603 - the pinned CLI is a development dependency
        ["node", str(producer), "statement", str(CONTRACT / "matrix-roster.json"), "--format", "codemeta"],  # noqa: S607
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    attribution = json.loads(result.stdout)
    expected = json.loads((CONTRACT / "matrix-attribution.json").read_text(encoding="utf-8"))
    assert attribution == expected, "Matrix must emit the hand-checked linked Person/Role attribution fragment"
    assert "only within this document" in result.stderr
    assert "omits scores and contribution levels" in result.stderr
    for name in FILES:
        shutil.copyfile(CONTRACT / name, tmp_path / name)
    path = tmp_path / "codemeta.json"
    source = json.loads(path.read_text(encoding="utf-8"))
    source.update(attribution)
    path.write_text(json.dumps(source, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return tmp_path


def test_matrix_cli_people_roles_and_idempotence(matrix_repo: Path) -> None:
    root = matrix_repo
    original = (root / "codemeta.json").read_bytes()
    expected = json.loads((CONTRACT / "expected.json").read_text(encoding="utf-8"))
    result = cli(root, "write")
    assert result.returncode == 0, result.stdout + result.stderr
    cff = YAML(typ="safe").load((root / "CITATION.cff").read_text(encoding="utf-8"))
    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    assert cff["authors"] == expected["cff_authors"]
    assert "contributors" not in cff
    assert zenodo["creators"] == expected["zenodo_creators"]
    assert zenodo["contributors"] == expected["zenodo_contributors"]
    assert (root / "codemeta.json").read_bytes() == original
    checked = cli(root, "check")
    assert checked.returncode == 0, checked.stdout + checked.stderr
    assert not [f for f in json.loads(checked.stdout)["findings"] if f["severity"] != "info"]
    before = snapshot(root)
    assert cli(root, "write").returncode == 0
    assert snapshot(root) == before

    (root / "citesync.toml").write_text('source = "CITATION.cff"\nmanifests = []\n', encoding="utf-8")
    cff_path = root / "CITATION.cff"
    cff_path.write_text(cff_path.read_text(encoding="utf-8").replace("1.0.0", "1.0.1"), encoding="utf-8")
    reverse = cli(root, "write")
    assert reverse.returncode == 0, reverse.stdout + reverse.stderr
    assert json.loads((root / "codemeta.json").read_text(encoding="utf-8")) == {
        **json.loads(original),
        "version": "1.0.1",
    }


@pytest.mark.parametrize(("chosen_type", "target_present"), [(None, True), ("Researcher", True), ("Researcher", False)])
def test_matrix_new_zenodo_contributor_needs_explicit_opt_in(
    matrix_repo: Path,
    chosen_type: str | None,
    *,
    target_present: bool,
) -> None:
    root = matrix_repo
    path = root / ".zenodo.json"
    zenodo = json.loads(path.read_text(encoding="utf-8"))
    original_people = [{"name": "Carberry, Josiah", "type": "Other"}]
    if target_present:
        zenodo["contributors"] = [] if chosen_type else original_people
    else:
        del zenodo["contributors"]
    path.write_text(json.dumps(zenodo) + "\n", encoding="utf-8")
    if chosen_type:
        with (root / "citesync.toml").open("a", encoding="utf-8") as config:
            config.write(f'zenodo-contributor-type = "{chosen_type}"\n')
    result = cli(root, "write")
    actual = json.loads(path.read_text(encoding="utf-8")).get("contributors")
    if not target_present:
        assert result.returncode == 0, result.stdout + result.stderr
        assert actual is None
    elif chosen_type:
        assert result.returncode == 0, result.stdout + result.stderr
        assert actual == [{"name": "Johnson, Katherine", "type": chosen_type}]
        assert cli(root, "check").returncode == 0
        before = snapshot(root)
        assert cli(root, "write").returncode == 0
        assert snapshot(root) == before
    else:
        assert result.returncode == 1
        assert "Zenodo needs a type" in result.stdout
        assert actual == original_people

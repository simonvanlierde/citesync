import json
from pathlib import Path

import pytest

from citesync import cli
from citesync.check import check
from citesync.config import load_config
from citesync.errors import CheckError
from citesync.write import init, write

CFF = """\
cff-version: 1.2.0
message: Cite this software.
title: cml-ia-factors
type: software
version: 0.1.0
license: MIT
authors:
  - family-names: van Lierde
    given-names: Simon
    orcid: https://orcid.org/0009-0006-6953-909X
keywords:
  - LCA
  - Brightway
"""


def test_write_and_check_dataset_codemeta_with_separate_licence(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'files = ["codemeta.json"]\n'
        'dataset-codemeta = "dataset.codemeta.json"\n'
        'dataset-license = "LicenseRef-CML-IA-no-licence-stated"\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    before, _, _ = check(tmp_path, cfg)
    assert {(f.file, f.rule) for f in before if f.severity == "error"} == {
        ("codemeta.json", "file-missing"),
        ("dataset.codemeta.json", "file-missing"),
    }

    write(tmp_path, cfg)
    after, _, _ = check(tmp_path, cfg)
    assert [f for f in after if f.severity == "error"] == []

    software = json.loads((tmp_path / "codemeta.json").read_text(encoding="utf-8"))
    dataset = json.loads((tmp_path / "dataset.codemeta.json").read_text(encoding="utf-8"))
    assert software["@type"] == "SoftwareSourceCode"
    assert software["license"] == "https://spdx.org/licenses/MIT"
    assert dataset["@type"] == "Dataset"
    assert dataset["license"] == "LicenseRef-CML-IA-no-licence-stated"
    assert dataset["name"] == "cml-ia-factors"
    assert dataset["version"] == "0.1.0"


def test_update_and_autodiscover_dataset_codemeta(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'dataset-license = "CC-BY-4.0"\n',
        encoding="utf-8",
    )
    write(tmp_path, load_config(tmp_path))
    assert (tmp_path / "dataset.codemeta.json").is_file()

    # Bump version in CITATION.cff and drop dataset-codemeta from config to test auto-discovery.
    (tmp_path / "CITATION.cff").write_text(CFF.replace("version: 0.1.0", "version: 0.2.0"), encoding="utf-8")
    found, _, _ = check(tmp_path, load_config(tmp_path))
    assert any(f.file == "dataset.codemeta.json" and f.term == "version" for f in found)

    write(tmp_path, load_config(tmp_path))
    clean, _, _ = check(tmp_path, load_config(tmp_path))
    assert [f for f in clean if f.severity == "error"] == []
    assert json.loads((tmp_path / "dataset.codemeta.json").read_text(encoding="utf-8"))["version"] == "0.2.0"


def test_cff_data_reference_licence_fallback(tmp_path: Path) -> None:
    cff_with_ref = CFF + (
        "references:\n"
        "  - type: data\n"
        "    title: Upstream dataset\n"
        "    authors:\n"
        "      - name: Example Lab\n"
        "    license: CC-BY-4.0\n"
    )
    (tmp_path / "CITATION.cff").write_text(cff_with_ref, encoding="utf-8")
    cfg = load_config(tmp_path, dataset_codemeta="manifests/dataset.codemeta.json")
    write(tmp_path, cfg)
    dataset = json.loads((tmp_path / "manifests/dataset.codemeta.json").read_text(encoding="utf-8"))
    assert dataset["license"] == "https://spdx.org/licenses/CC-BY-4.0"
    clean, _, _ = check(tmp_path, cfg)
    assert [f for f in clean if f.severity == "error"] == []


def test_cli_flags_override_and_default_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    code = cli.main(
        ["write", "--root", str(tmp_path), "--dataset-license", "LicenseRef-CML-IA-no-licence-stated", "-q"]
    )
    assert code == 0
    assert (tmp_path / "dataset.codemeta.json").is_file()
    code = cli.main(
        ["check", "--root", str(tmp_path), "--dataset-license", "LicenseRef-CML-IA-no-licence-stated", "-q"]
    )
    assert code == 0
    capsys.readouterr()


def test_init_ignores_dataset_codemeta(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    write(tmp_path, load_config(tmp_path, dataset_license="CC0-1.0"))
    (tmp_path / "CITATION.cff").unlink()
    (tmp_path / "codemeta.json").write_text(
        json.dumps(
            {
                "@context": "https://w3id.org/codemeta/3.0",
                "name": "cml-ia-factors",
                "license": "MIT",
                "author": [{"@type": "Person", "givenName": "Simon", "familyName": "van Lierde"}],
            }
        ),
        encoding="utf-8",
    )
    text, _, _, _ = init(tmp_path, load_config(tmp_path), dry_run=True)
    assert "license: MIT" in text
    assert "CC0-1.0" not in text


@pytest.mark.parametrize(
    "toml",
    [
        'dataset-codemeta = "codemeta.json"\n',
        'dataset-codemeta = "dataset.txt"\n',
        'dataset-codemeta = "../outside.json"\n',
        'dataset-license = "   "\n',
    ],
    ids=["codemeta-json", "non-json", "outside-root", "empty-license"],
)
def test_invalid_dataset_codemeta_config(tmp_path: Path, toml: str) -> None:
    (tmp_path / "citesync.toml").write_text(toml, encoding="utf-8")
    with pytest.raises(CheckError):
        load_config(tmp_path)

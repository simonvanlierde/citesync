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


@pytest.mark.parametrize("licence", ["CC-BY-4.0", "https://spdx.org/licenses/CC-BY-4.0"])
def test_rewrite_dataset_codemeta_on_licence_mismatch(tmp_path: Path, licence: str) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(f'dataset-license = "{licence}"\n', encoding="utf-8")
    (tmp_path / "dataset.codemeta.json").write_text(
        json.dumps(
            {
                "@context": "https://w3id.org/codemeta/3.0",
                "@type": "Dataset",
                "name": "cml-ia-factors",
                "version": "0.1.0",
                "license": "https://spdx.org/licenses/MIT",
                "author": [
                    {
                        "@type": "Person",
                        "givenName": "Simon",
                        "familyName": "van Lierde",
                        "@id": "https://orcid.org/0009-0006-6953-909X",
                    }
                ],
                "keywords": ["LCA", "Brightway"],
            }
        ),
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    found, _, _ = check(tmp_path, cfg)
    assert any(f.file == "dataset.codemeta.json" and f.term == "license" for f in found)

    write(tmp_path, cfg)
    clean, _, _ = check(tmp_path, cfg)
    assert [f for f in clean if f.severity == "error"] == []
    assert (
        json.loads((tmp_path / "dataset.codemeta.json").read_text(encoding="utf-8"))["license"]
        == "https://spdx.org/licenses/CC-BY-4.0"
    )


def test_unmapped_reference_licence_is_not_used(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(
        CFF + "references:\n  - type: data\n    title: Other work\n    license: CC-BY-4.0\n",
        encoding="utf-8",
    )
    cfg = load_config(tmp_path, dataset_codemeta="metadata.json")
    write(tmp_path, cfg)
    assert (
        json.loads((tmp_path / "metadata.json").read_text(encoding="utf-8"))["license"]
        == "https://spdx.org/licenses/MIT"
    )


def test_cli_flags_override_and_default_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'dataset-codemeta = "ignored.json"\ndataset-license = "MIT"\n', encoding="utf-8"
    )
    code = cli.main(
        [
            "write",
            "--root",
            str(tmp_path),
            "--dataset-codemeta",
            "custom.codemeta.json",
            "--dataset-license",
            "LicenseRef-CML-IA-no-licence-stated",
            "-q",
        ]
    )
    assert code == 0
    assert (tmp_path / "custom.codemeta.json").is_file()
    assert not (tmp_path / "ignored.json").exists()
    assert (
        json.loads((tmp_path / "custom.codemeta.json").read_text(encoding="utf-8"))["license"]
        == "LicenseRef-CML-IA-no-licence-stated"
    )
    code = cli.main(
        [
            "check",
            "--root",
            str(tmp_path),
            "--dataset-codemeta",
            "custom.codemeta.json",
            "--dataset-license",
            "LicenseRef-CML-IA-no-licence-stated",
            "-q",
        ]
    )
    assert code == 0
    capsys.readouterr()


def test_exports_exclude_dataset_codemeta_and_advice_handles_custom_path(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cff_no_lic = CFF.replace("license: MIT\n", "")
    (tmp_path / "CITATION.cff").write_text(cff_no_lic, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'dataset-license = "CC-BY-4.0"\nexports = ["citation.csl.json"]\n', encoding="utf-8"
    )
    assert cli.main(["write", "--root", str(tmp_path), "-q"]) == 0
    assert cli.main(["check", "--root", str(tmp_path), "-q"]) == 0

    # An unfixable finding with a term on dataset.codemeta.json must not crash advice() in cli write.
    data = json.loads((tmp_path / "dataset.codemeta.json").read_text(encoding="utf-8"))
    data["madeUpKey"] = "x"
    (tmp_path / "dataset.codemeta.json").write_text(json.dumps(data), encoding="utf-8")
    assert cli.main(["write", "--root", str(tmp_path)]) == 1
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


@pytest.mark.parametrize(
    "rel",
    ["metadata/croissant.json", "metadata/ro-crate-metadata.json", "metadata/codemeta.json", "metadata/package.json"],
)
def test_nested_reserved_dataset_path_is_rejected(tmp_path: Path, rel: str) -> None:
    with pytest.raises(CheckError, match="dataset-codemeta"):
        load_config(tmp_path, dataset_codemeta=rel)


@pytest.mark.parametrize(
    "licence",
    ["http://example.org/Licence(foo)", "https://example.org/Licence(foo)", "HTTPS://example.org/Licence(foo)"],
)
def test_dataset_license_url_survives_creation_and_repair(tmp_path: Path, licence: str) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    cfg = load_config(tmp_path, dataset_license=licence)
    write(tmp_path, cfg)
    path = tmp_path / "dataset.codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["license"] == licence
    for wrong in ["https://example.org/Licencefoo", "https://example.org/licence(foo)"]:
        data["license"] = wrong
        path.write_text(json.dumps(data), encoding="utf-8")
        assert any(f.term == "license" and f.file == path.name for f in check(tmp_path, cfg)[0])
        write(tmp_path, cfg)
        assert json.loads(path.read_text(encoding="utf-8"))["license"] == licence
    assert not [f for f in check(tmp_path, cfg)[0] if f.severity == "error"]


@pytest.mark.parametrize("rel", ["dataset.codemeta.json", "metadata/data.json", "./metadata/data.json"])
def test_required_fields_apply_to_dataset_codemeta(tmp_path: Path, rel: str) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        f'required-fields = {{ "{rel}" = ["name", "version", "author", "license"] }}\n'
        f'dataset-codemeta = "{rel}"\ndataset-license = "CC0-1.0"\n',
        encoding="utf-8",
    )
    cfg = load_config(tmp_path)
    rel = str(Path(rel))
    missing, _, _ = check(tmp_path, cfg)
    assert {(f.file, f.term) for f in missing if f.rule == "required-field-missing"} == {
        (rel, term) for term in ["name", "version", "author", "license"]
    }
    write(tmp_path, cfg)
    assert not [f for f in check(tmp_path, cfg)[0] if f.severity == "error"]
    path = tmp_path / rel
    data = json.loads(path.read_text(encoding="utf-8"))
    del data["version"]
    path.write_text(json.dumps(data), encoding="utf-8")
    found, _, _ = check(tmp_path, cfg)
    assert any(f.file == rel and f.term == "version" and f.rule == "required-field-missing" for f in found)


@pytest.mark.parametrize("rel", ["dataset.codemeta.json", "metadata/data.json"])
def test_required_dataset_symlink_cannot_escape_root(tmp_path: Path, rel: str) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(tmp_path / "outside.json")
    (repo / "citesync.toml").write_text(
        f'dataset-codemeta = "{rel}"\nrequired-fields = {{ "{rel}" = ["license"] }}\n',
        encoding="utf-8",
    )
    with pytest.raises(CheckError, match="resolves outside"):
        load_config(repo)


def test_required_default_dataset_is_read_with_custom_dataset_configured(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'dataset-codemeta = "metadata/data.json"\nrequired-fields = { "dataset.codemeta.json" = ["license"] }\n',
        encoding="utf-8",
    )
    (tmp_path / "dataset.codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/3.0", "@type": "Dataset", "name": "Example"}),
        encoding="utf-8",
    )
    found, _, _ = check(tmp_path, load_config(tmp_path))
    assert any(
        f.file == "dataset.codemeta.json" and f.term == "license" and f.rule == "required-field-missing" for f in found
    )


@pytest.mark.parametrize(
    "first", ["http://example.org/Licence(foo)", "https://example.org/Licence(foo)", "HTTPS://example.org/Licence(foo)"]
)
def test_url_and_spdx_licence_list_preserves_each_value(tmp_path: Path, first: str) -> None:
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "Example", "license": [first, "MIT"]}),
        encoding="utf-8",
    )
    cfg = load_config(tmp_path, source="codemeta.json", dataset_codemeta="dataset.codemeta.json")
    write(tmp_path, cfg)
    data = json.loads((tmp_path / "dataset.codemeta.json").read_text(encoding="utf-8"))
    assert data["license"] == [first, "https://spdx.org/licenses/MIT"]
    assert not [f for f in check(tmp_path, cfg)[0] if f.severity == "error"]


def test_dataset_licence_rewrites_when_source_format_has_no_licence_slot(tmp_path: Path) -> None:
    (tmp_path / "Project.toml").write_text('name = "Tidepool"\nversion = "0.1.0"\n', encoding="utf-8")
    cfg = load_config(tmp_path, source="Project.toml", dataset_license="CC0-1.0")
    write(tmp_path, cfg)
    path = tmp_path / "dataset.codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["license"] = "MIT"
    path.write_text(json.dumps(data), encoding="utf-8")
    write(tmp_path, cfg)
    assert json.loads(path.read_text(encoding="utf-8"))["license"] == "CC0-1.0"


def test_dataset_version_checked_when_source_has_no_licence(tmp_path: Path) -> None:
    source = tmp_path / "CITATION.cff"
    source.write_text(CFF.replace("license: MIT\n", ""), encoding="utf-8")
    cfg = load_config(tmp_path, dataset_codemeta="dataset.codemeta.json")
    write(tmp_path, cfg)
    path = tmp_path / "dataset.codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["license"] = "MIT"
    path.write_text(json.dumps(data), encoding="utf-8")
    source.write_text(source.read_text(encoding="utf-8").replace("0.1.0", "0.2.0"), encoding="utf-8")
    found, _, _ = check(tmp_path, cfg)
    assert any(f.file == path.name and f.rule == "version-mismatch" for f in found)
    assert not [f for f in found if f.rule == "license-mismatch"]


def test_dataset_and_export_cannot_share_a_destination(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'dataset-codemeta = "citation.csl.json"\ndataset-license = "CC0-1.0"\nexports = ["./citation.csl.json"]\n',
        encoding="utf-8",
    )
    path = tmp_path / "citation.csl.json"
    original = json.dumps({"@context": "https://w3id.org/codemeta/3.0", "@type": "Dataset", "license": "MIT"})
    path.write_text(original, encoding="utf-8")
    with pytest.raises(CheckError, match="same file"):
        write(tmp_path, load_config(tmp_path))
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("configured", [True, False])
def test_dataset_alias_cannot_rewrite_software_metadata(tmp_path: Path, *, configured: bool) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    software = tmp_path / "codemeta.json"
    original = json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "cml-ia-factors", "license": "MIT"})
    software.write_text(original, encoding="utf-8")
    (tmp_path / "dataset.codemeta.json").symlink_to(software.name)
    config = load_config(tmp_path, dataset_license="CC0-1.0") if configured else load_config(tmp_path)
    with pytest.raises(CheckError, match="same file"):
        write(tmp_path, config)
    assert software.read_text(encoding="utf-8") == original


def test_dataset_symlink_to_distinct_inside_file_still_updates(tmp_path: Path) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    target = tmp_path / "metadata.json"
    target.write_text(json.dumps({"@context": "https://w3id.org/codemeta/3.0", "license": "MIT"}), encoding="utf-8")
    (tmp_path / "dataset.codemeta.json").symlink_to(target.name)
    write(tmp_path, load_config(tmp_path, dataset_license="CC0-1.0"))
    assert json.loads(target.read_text(encoding="utf-8"))["license"] == "CC0-1.0"

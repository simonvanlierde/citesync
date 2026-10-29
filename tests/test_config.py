"""Config discovery in the D7 order (first found wins), validation, and `citesync config`."""

import json
from pathlib import Path

import pytest

from citesync.cli import main
from citesync.config import load_config

CFF = 'cff-version: 1.2.0\nmessage: "m"\ntitle: "x"\n'

# Each location names a different source, so the one in use shows which file won. In winning order.
LOCATIONS = [
    ("citesync.toml", "citesync.toml", 'source = "codemeta.json"\n'),
    (".citesync.toml", ".citesync.toml", 'source = ".zenodo.json"\n'),
    ("pyproject.toml [tool.citesync]", "pyproject.toml", '[tool.citesync]\nsource = "pyproject.toml"\n'),
    (
        "Cargo.toml [workspace.metadata.citesync]",
        "Cargo.toml",
        (
            '[workspace.metadata.citesync]\nsource = "Cargo.toml"\n\n'
            '[package.metadata.citesync]\nsource = "package.json"\n'
        ),
    ),
    ("Cargo.toml [package.metadata.citesync]", "Cargo.toml", '[package.metadata.citesync]\nsource = "package.json"\n'),
    ('package.json "citesync"', "package.json", json.dumps({"citesync": {"source": "src/CITATION.cff"}})),
]
SOURCES = ["codemeta.json", ".zenodo.json", "pyproject.toml", "Cargo.toml", "package.json", "src/CITATION.cff"]


def test_first_location_wins_down_the_chain(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """With every location present, remove the winner one at a time; the next one wins."""
    for i, (_, name, text) in enumerate(LOCATIONS):
        if i != 4:  # LOCATIONS[3] holds both Cargo.toml tables
            (tmp_path / name).write_text(text, encoding="utf-8")

    for (origin, name, _), source in zip(LOCATIONS, SOURCES, strict=True):
        config = load_config(tmp_path)
        assert (config.origin, config.source) == (origin, source)
        assert main(["config", "--root", str(tmp_path)]) == 0
        out = capsys.readouterr().out
        assert out.startswith(f"# from {origin}\nsource = {json.dumps(source)}\n")
        # Remove the winner: the whole file, or for Cargo.toml the workspace table first.
        if origin == "Cargo.toml [workspace.metadata.citesync]":
            (tmp_path / name).write_text(LOCATIONS[4][2], encoding="utf-8")
        else:
            (tmp_path / name).unlink()
    assert load_config(tmp_path).origin == "defaults"


def test_flag_overrides_config(tmp_path: Path) -> None:
    (tmp_path / "citesync.toml").write_text('source = "codemeta.json"\n', encoding="utf-8")
    assert load_config(tmp_path, "package.json").source == "package.json"


def test_config_prints_defaults(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["config", "--root", str(tmp_path)]) == 0
    assert capsys.readouterr().out == (
        "# from defaults\n"
        'source = "CITATION.cff"\n'
        'codemeta_version = "3.0"\n'
        "# files: not set, so every citation file present\n"
        "# manifests: not set, so every release manifest at the repo root\n"
        "write_manifests = []\n"
        "keywords_case_sensitive = false\n"
        "ignore = []\n"
    )


def test_keywords_case_sensitive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "citesync.toml").write_text("keywords_case_sensitive = true\n", encoding="utf-8")
    assert load_config(tmp_path).keywords_case_sensitive is True
    assert main(["config", "--root", str(tmp_path)]) == 0
    assert "keywords_case_sensitive = true\n" in capsys.readouterr().out


def test_write_manifests_all_expands(tmp_path: Path) -> None:
    (tmp_path / "citesync.toml").write_text('write_manifests = "all"\n', encoding="utf-8")
    assert len(load_config(tmp_path).write_manifests) == 8


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('sources = "CITATION.cff"\n', "citesync.toml: unknown key sources"),
        ('write_manifests = ["keyword"]\n', "write_manifests must be 'all' or a list of"),
        ('write_manifests = "some"\n', "write_manifests must be 'all' or a list of"),
        ('codemeta_version = "3.2"\n', "codemeta_version must be one of"),
        ('manifests = ["CITATION.cff"]\n', "manifests must name one of"),
        ('manifests = ["../x/package.json"]\n', "must be relative to the repo root"),
        ('files = "codemeta.json"\n', "files must be a list of paths"),
        ('keywords_case_sensitive = "yes"\n', "keywords_case_sensitive must be true or false"),
        ("source = \n", "citesync.toml: cannot read config"),
        ('ignore = ["version"]\n', "ignore must be a list of rule ids from name-mismatch,"),
        ('ignore = ["unreadable"]\n', "ignore must be a list of rule ids"),
    ],
)
def test_bad_config_exits_2(text: str, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(text, encoding="utf-8")
    assert main(["check", "--root", str(tmp_path)]) == 2
    assert message in capsys.readouterr().err
    assert main(["config", "--root", str(tmp_path)]) == 2

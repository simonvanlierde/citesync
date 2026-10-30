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
        assert out.startswith(f"# root: {tmp_path}\n# from {origin}\nsource = {json.dumps(source)}\n")
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
        f"# root: {tmp_path}\n"
        "# from defaults\n"
        'source = "CITATION.cff"\n'
        "# codemeta-version: not set, so any supported @context passes\n"
        "# files: not set, so every citation file present\n"
        "# manifests: not set, so every release manifest at the repo root\n"
        "write-manifests = []\n"
        "keywords-case-sensitive = false\n"
        "keywords-ignore-separators = false\n"
        "ignore = []\n"
    )


def test_keywords_ignore_separators(tmp_path: Path) -> None:
    (tmp_path / "citesync.toml").write_text("keywords-ignore-separators = true\n", encoding="utf-8")
    assert load_config(tmp_path).keywords_ignore_separators


def test_keywords_case_sensitive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "citesync.toml").write_text(
        'keywords-case-sensitive = true\ncodemeta-version = "4.0"\n', encoding="utf-8"
    )
    config = load_config(tmp_path)
    assert (config.keywords_case_sensitive, config.codemeta_version) == (True, "4.0")
    assert main(["config", "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert 'codemeta-version = "4.0"\n' in out
    assert "keywords-case-sensitive = true\n" in out


def test_write_manifests_all_expands(tmp_path: Path) -> None:
    (tmp_path / "citesync.toml").write_text('write-manifests = "all"\n', encoding="utf-8")
    assert len(load_config(tmp_path).write_manifests) == 6


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('sources = "CITATION.cff"\n', "citesync.toml: unknown key sources"),
        ('write-manifests = ["keyword"]\n', "write-manifests: 'keyword' is not a term"),
        ('write-manifests = "some"\n', "write-manifests: 'some' is not a term"),
        ("write-manifests = [1]\n", "write-manifests must be 'all' or a list of"),
        ('write_manifests = "all"\n', "citesync.toml: unknown key write_manifests"),
        ('codemeta-version = "3.2"\n', "codemeta-version must be one of"),
        ('codemeta_version = "3.0"\n', "citesync.toml: unknown key codemeta_version"),
        ("keywords_case_sensitive = true\n", "citesync.toml: unknown key keywords_case_sensitive"),
        ('manifests = ["CITATION.cff"]\n', "manifests must name one of"),
        ('manifests = ["../x/package.json"]\n', "must be relative to the repo root"),
        ('files = "codemeta.json"\n', "files must be a list of paths"),
        ('keywords-case-sensitive = "yes"\n', "keywords-case-sensitive must be true or false"),
        ("source = \n", "citesync.toml:1:10: Invalid value"),
        ('ignore = ["version"]\n', "ignore entry 'version' is not a rule id"),
        ('ignore = ["unreadable"]\n', "ignore entry 'unreadable' can't be ignored"),
        ('ignore = "version-mismatch"\n', "ignore must be a list of rule ids"),
    ],
)
def test_bad_config_exits_2(text: str, message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(text, encoding="utf-8")
    assert main(["check", "--root", str(tmp_path)]) == 2
    assert message in capsys.readouterr().err
    assert main(["config", "--root", str(tmp_path)]) == 2


def test_root_is_found_from_a_subdirectory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Without --root, citesync walks up to the citation files, as ruff walks up to its config."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "y"}), encoding="utf-8"
    )
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    monkeypatch.chdir(tmp_path / "src" / "pkg")
    assert main(["check"]) == 1
    assert capsys.readouterr().out.startswith("codemeta.json: error[name-mismatch]")


@pytest.mark.parametrize(("marker", "content"), [(origin, text) for origin, _, text in LOCATIONS[::2]])
def test_root_is_found_by_its_config(
    marker: str, content: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    name = marker.split(maxsplit=1)[0]
    (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / "sub").mkdir()
    monkeypatch.chdir(tmp_path / "sub")
    assert main(["config"]) == 0
    assert capsys.readouterr().out.startswith(f"# root: {tmp_path}\n# from {marker}")


def test_the_walk_stops_at_the_git_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A submodule (its .git is a file) or a nested repo is its own root: the outer repo's files are not its."""
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    inner = tmp_path / "vendor" / "lib"
    inner.mkdir(parents=True)
    (inner / ".git").write_text("gitdir: ../../.git/modules/lib\n", encoding="utf-8")
    (inner / "src").mkdir()
    monkeypatch.chdir(inner / "src")
    assert main(["check"]) == 2
    assert "CITATION.cff" in capsys.readouterr().err

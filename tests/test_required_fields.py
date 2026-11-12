"""Opt-in completeness checks leave omission preservation unchanged."""

import json
import tempfile
from pathlib import Path

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from citesync.cli import main
from citesync.config import load_config, render
from citesync.mapping import TERMS

CFF = "cff-version: 1.2.0\nmessage: Cite this software\ntitle: tidepool\nversion: 1.2.3\ndoi: 10.5555/12345678\n"
REQUIRED = 'required-fields = { "codemeta.json" = ["version", "identifier"] }\n'


def test_removed_generated_fields_fail_only_when_required(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('files = ["codemeta.json"]\n', encoding="utf-8")
    assert main(["write", "--root", str(tmp_path)]) == 0
    target = tmp_path / "codemeta.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data.pop("version") == "1.2.3"
    assert data.pop("identifier")
    target.write_text(json.dumps(data), encoding="utf-8")
    assert main(["check", "--root", str(tmp_path)]) == 0
    assert main(["write", "--root", str(tmp_path)]) == 0
    assert json.loads(target.read_text(encoding="utf-8")) == data
    (tmp_path / "citesync.toml").write_text(REQUIRED, encoding="utf-8")
    capsys.readouterr()
    assert main(["check", "--root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    missing = [f for f in report["findings"] if f["rule"] == "required-field-missing"]
    assert {(f["file"], f["term"], f["severity"]) for f in missing} == {
        ("codemeta.json", "version", "error"),
        ("codemeta.json", "identifier", "error"),
    }
    assert main(["write", "--root", str(tmp_path)]) == 1
    assert json.loads(target.read_text(encoding="utf-8")) == data


@pytest.mark.parametrize("source_knows", [True, False])
@pytest.mark.parametrize("target", [None, {}, {"version": None, "identifier": ""}, {"version": "  "}])
def test_absence_fails_without_assuming_source_knowledge(
    tmp_path: Path, target: dict[str, object] | None, capsys: pytest.CaptureFixture[str], *, source_knows: bool
) -> None:
    source = CFF if source_knows else CFF.split("version: 1.2.3", maxsplit=1)[0]
    (tmp_path / "CITATION.cff").write_text(source, encoding="utf-8")
    if target is not None:
        (tmp_path / "codemeta.json").write_text(
            json.dumps({"@context": "https://w3id.org/codemeta/3.0", **target}), encoding="utf-8"
        )
    (tmp_path / "citesync.toml").write_text(REQUIRED, encoding="utf-8")
    assert main(["check", "--root", str(tmp_path)]) == 1
    text = capsys.readouterr().out
    assert "error[required-field-missing]" in text
    assert "identifier:" in text
    assert "version:" in text
    assert "source holds" not in text


def test_complete_target_passes_and_config_round_trips(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    import tomllib  # noqa: PLC0415

    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/3.0", "version": "1.2.3", "identifier": "10.5555/12345678"}),
        encoding="utf-8",
    )
    (tmp_path / "citesync.toml").write_text(REQUIRED, encoding="utf-8")
    assert main(["check", "--root", str(tmp_path)]) == 0
    capsys.readouterr()
    config = load_config(tmp_path)
    assert main(["config", "--root", str(tmp_path)]) == 0
    rendered = capsys.readouterr().out
    assert tomllib.loads(rendered)["required-fields"] == {"codemeta.json": ["version", "identifier"]}
    (tmp_path / "citesync.toml").write_text(rendered, encoding="utf-8")
    assert load_config(tmp_path).required_fields == config.required_fields


@pytest.mark.parametrize(
    ("setting", "message"),
    [
        ("required-fields = []", "must be a table"),
        ('required-fields = { "codemeta.json" = "version" }', "non-empty list"),
        ('required-fields = { "codemeta.json" = [] }', "non-empty list"),
        ('required-fields = { "codemeta.json" = [1] }', "non-empty list"),
        ('required-fields = { "codemeta.json" = ["doi"] }', "not a supported term"),
        ('required-fields = { "codemeta.json" = ["author.@id"] }', "not a supported term"),
        ('required-fields = { "codemeta.json" = ["publisher"] }', "not a supported term"),
        ('required-fields = { "pyproject.toml" = ["identifier"] }', "cannot represent"),
        ('required-fields = { "CITATION.cff" = ["contributor"] }', "cannot represent"),
        ('required-fields = { "CITATION.bib" = ["version"] }', "must name one of"),
        ('required-fields = { "../codemeta.json" = ["version"] }', "relative to the repo root"),
        ('required-fields = { "/codemeta.json" = ["version"] }', "relative to the repo root"),
        ('required-fields = { "C:/codemeta.json" = ["version"] }', "POSIX path"),
        ("required-fields = { 'dir\\file/codemeta.json' = ['version'] }", "POSIX path"),
        ('required-fields = { "dir\\u0000/codemeta.json" = ["version"] }', "POSIX path"),
    ],
)
def test_invalid_requirements_fail_as_config_errors(
    tmp_path: Path, setting: str, message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "citesync.toml").write_text(setting, encoding="utf-8")
    assert main(["config", "--root", str(tmp_path)]) == 3
    assert message in capsys.readouterr().err
    assert main(["check", "--root", str(tmp_path), "--json"]) == 3
    report = json.loads(capsys.readouterr().out)
    assert message in report["errors"][0]["message"]


@pytest.mark.parametrize("path", ["nested/codemeta.json", "package.json", "pyproject.toml", "croissant.json"])
def test_requirements_apply_outside_discovery(tmp_path: Path, path: str, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    target = tmp_path / path
    target.parent.mkdir(exist_ok=True)
    if path == "pyproject.toml":
        target.write_text('[project]\nname = "tidepool"\n', encoding="utf-8")
    else:
        target.write_text(json.dumps({"@context": "https://w3id.org/codemeta/3.0", "private": True}), encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        f'files = []\nrequired-fields = {{ "{path}" = ["version"] }}\n', encoding="utf-8"
    )
    assert main(["check", "--root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert any(f["file"] == path and f["rule"] == "required-field-missing" for f in report["findings"])
    assert report["summary"]["files"] == 2


@pytest.mark.parametrize("content", ["{", '{"@context": "unsupported"}', "[]"])
def test_unreadable_required_target_cannot_pass(
    tmp_path: Path, content: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(content, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text("files = []\n" + REQUIRED, encoding="utf-8")
    assert main(["check", "--root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert any(f["rule"] == "unreadable" for f in report["findings"])


def test_required_symlink_cannot_escape_root(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "citesync.toml").write_text(REQUIRED, encoding="utf-8")
    (repo / "codemeta.json").symlink_to(tmp_path / "codemeta.json")
    assert main(["config", "--root", str(repo)]) == 3
    assert "resolves outside the repo root" in capsys.readouterr().err


def test_identifier_requires_doi_not_just_any_identifier(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/3.0", "version": "1.2.3", "identifier": "tidepool"}),
        encoding="utf-8",
    )
    (tmp_path / "citesync.toml").write_text(REQUIRED, encoding="utf-8")
    assert main(["check", "--root", str(tmp_path)]) == 1
    assert "identifier: required value is missing" in capsys.readouterr().out


@given(st.lists(st.sampled_from(TERMS), min_size=1), st.sampled_from(["", "nested/", "métadata/", "🦀/"]))
@example(terms=["name"], directory="🦀/")
def test_required_terms_preserve_order_and_round_trip(terms: list[str], directory: str) -> None:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        path = root / "citesync.toml"
        path.write_text(f'required-fields = {{ "{directory}codemeta.json" = {json.dumps(terms)} }}', encoding="utf-8")
        config = load_config(root)
        assert config.required_fields == ((f"{directory}codemeta.json", tuple(dict.fromkeys(terms))),)
        path.write_text(render(config), encoding="utf-8")
        assert load_config(root).required_fields == config.required_fields


def test_required_path_aliases_merge_terms(tmp_path: Path) -> None:
    (tmp_path / "citesync.toml").write_text(
        'required-fields = { "./codemeta.json" = ["version"], "codemeta.json" = ["identifier"] }',
        encoding="utf-8",
    )
    assert load_config(tmp_path).required_fields == (("codemeta.json", ("version", "identifier")),)


def test_required_rule_can_be_ignored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(REQUIRED + 'ignore = ["required-field-missing"]', encoding="utf-8")
    assert main(["check", "--root", str(tmp_path)]) == 0
    assert "required-field-missing" not in capsys.readouterr().out


@pytest.mark.parametrize("setting", ['manifests = ["package.json"]', 'source = "package.json"'])
def test_missing_prerequisite_still_stops_discovery(
    tmp_path: Path, setting: str, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        setting + '\nrequired-fields = { "package.json" = ["version"] }', encoding="utf-8"
    )
    assert main(["check", "--root", str(tmp_path), "--json"]) == 3
    report = json.loads(capsys.readouterr().out)
    assert "missing" in report["errors"][0]["message"]
    assert "findings" not in report


def test_multiple_requirements_keep_file_counts_and_error_locations(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF.split("version: 1.2.3", maxsplit=1)[0], encoding="utf-8")
    for directory, content in [
        ("broken", '{\n  "version":\n}'),
        ("complete", '{"@context": "https://w3id.org/codemeta/3.0", "version": "1.2.3"}'),
        ("empty", '{"@context": "https://w3id.org/codemeta/3.0"}'),
    ]:
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "codemeta.json").write_text(content, encoding="utf-8")
    (tmp_path / "citesync.toml").write_text(
        'required-fields = { "missing/codemeta.json" = ["version", "identifier"], '
        '"broken/codemeta.json" = ["version"], "complete/codemeta.json" = ["version"], '
        '"empty/codemeta.json" = ["version"] }',
        encoding="utf-8",
    )
    assert main(["check", "--root", str(tmp_path), "--json"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["summary"]["files"] == 4
    missing = [f for f in report["findings"] if f["rule"] == "required-field-missing"]
    assert {(f["file"], f["term"], f["message"]) for f in missing} == {
        ("missing/codemeta.json", "version", "required file is missing"),
        ("missing/codemeta.json", "identifier", "required file is missing"),
        ("empty/codemeta.json", "version", "required value is missing or empty"),
    }
    unreadable = [f for f in report["findings"] if f["rule"] == "unreadable"]
    assert len(unreadable) == 1
    assert (unreadable[0]["file"], unreadable[0]["message"], unreadable[0]["line"], unreadable[0]["column"]) == (
        "broken/codemeta.json",
        "Expecting value",
        3,
        1,
    )

"""`citesync write` against committed expected files, plus what it must leave alone."""

import json
import re
import shutil
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from citesync.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic-agree"
PLANTED = Path(__file__).parent / "write" / "planted"
EXPECTED = Path(__file__).parent / "write" / "expected"
NAMES = ["CITATION.cff", "codemeta.json", ".zenodo.json", "pyproject.toml", "Cargo.toml", "package.json"]
MANIFESTS = ["pyproject.toml", "Cargo.toml", "package.json"]


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def _snapshot(root: Path) -> dict[str, bytes]:
    return {str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()}


def _expected(name: str) -> bytes:
    """``name`` once write has fixed its planted copy: the synthetic file, unless the planted one differs in layout."""
    return (EXPECTED / name if (EXPECTED / name).exists() else SYNTHETIC / name).read_bytes()


def _synthetic(root: Path, config: str = "") -> Path:
    shutil.copytree(SYNTHETIC, root)
    if config:
        (root / "citesync.toml").write_text(config, encoding="utf-8")
    return root


@pytest.mark.parametrize("name", NAMES)
def test_planted_disagreement_is_written_as_expected(
    name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = "codemeta.json" if name == "CITATION.cff" else "CITATION.cff"
    root = _synthetic(tmp_path / "repo", f'source = "{source}"\nwrite-manifests = "all"\n')
    shutil.copy(PLANTED / name, root / name)
    before = _snapshot(root)

    code, out, err = _run(capsys, "write", "--root", str(root))
    assert (code, out.splitlines()[0], err) == (0, f"wrote {name}", "")
    assert (root / name).read_bytes() == _expected(name)
    after = _snapshot(root)
    assert {k: v for k, v in after.items() if k != name} == {k: v for k, v in before.items() if k != name}

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert _snapshot(root) == after
    assert _run(capsys, "check", "-q", "--root", str(root)) == (0, "", "")


def test_manifests_are_left_alone_without_write_manifests(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    for name in MANIFESTS:
        shutil.copy(PLANTED / name, root / name)
    before = _snapshot(root)

    code, out, err = _run(capsys, "write", "--root", str(root))
    assert (code, err) == (1, "")
    assert _snapshot(root) == before
    lines = out.splitlines()[:-1]
    assert all(line.endswith("to write-manifests)") for line in lines)
    assert any("pyproject.toml" in line and line.endswith("add version to write-manifests)") for line in lines)
    assert any("Cargo.toml" in line and line.endswith("add keywords to write-manifests)") for line in lines)


def test_only_the_listed_manifest_fields_are_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'write-manifests = ["version"]\n')
    shutil.copy(PLANTED / "Cargo.toml", root / "Cargo.toml")

    code, out, _ = _run(capsys, "write", "--root", str(root))
    text = (root / "Cargo.toml").read_text(encoding="utf-8")
    assert code == 1
    assert 'version = "1.2.3"' in text
    assert "Grace Hopper" in text
    assert out.splitlines()[0] == "wrote Cargo.toml"
    assert all("version" not in line for line in out.splitlines()[1:-1])


def _comments(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.lstrip().startswith("#") or " # " in line]


@pytest.mark.parametrize("repo", sorted(p.parent.name for p in FIXTURES.glob("*/CITATION.cff")))
def test_cff_comments_survive_a_write(repo: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / repo
    root.mkdir()
    cff = (FIXTURES / repo / "CITATION.cff").read_text(encoding="utf-8")
    (root / "CITATION.cff").write_text(cff, encoding="utf-8")
    codemeta = {"@context": "https://w3id.org/codemeta/3.0", "name": "Planted", "keywords": ["planted"]}
    (root / "codemeta.json").write_text(json.dumps(codemeta), encoding="utf-8")

    code, out, _ = _run(capsys, "write", "--root", str(root), "--source", "codemeta.json")
    written = (root / "CITATION.cff").read_text(encoding="utf-8")
    assert (code, out.splitlines()[0]) == (0, "wrote CITATION.cff")
    assert _comments(cff)
    assert _comments(written) == _comments(cff)


@pytest.mark.parametrize("repo", sorted(p.parent.name for p in FIXTURES.glob("*/.zenodo.json")))
def test_zenodo_gains_no_version(repo: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / repo
    shutil.copytree(FIXTURES / repo, root)
    had_version = "version" in json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    cff = root / "CITATION.cff"
    cff.write_text(
        re.sub(r"^version: .*$", "version: 9.9.9", cff.read_text(encoding="utf-8"), flags=re.MULTILINE), "utf-8"
    )

    assert _run(capsys, "write", "--root", str(root))[1].startswith("wrote ")
    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    assert zenodo.get("version", None) == ("9.9.9" if had_version else None)


def test_cargo_workspace_keys_stay(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "jsonvet"
    shutil.copytree(FIXTURES / "jsonvet", root)
    member = "crates/jsonvet/Cargo.toml"
    (root / "citesync.toml").write_text(f'manifests = ["{member}"]\nwrite-manifests = "all"\n', encoding="utf-8")
    before = _snapshot(root)

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert _snapshot(root) == before
    [line, _] = out.splitlines()
    assert member in line
    assert line.endswith(" (edit it by hand)")


def test_virtual_workspace_is_written_through_workspace_package(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "jsonvet"
    shutil.copytree(FIXTURES / "jsonvet", root)
    (root / "citesync.toml").write_text('write-manifests = ["keywords"]\n', encoding="utf-8")
    before = (root / "Cargo.toml").read_text(encoding="utf-8")

    assert _run(capsys, "write", "--root", str(root))[1].startswith("wrote Cargo.toml\n")
    after = (root / "Cargo.toml").read_text(encoding="utf-8")
    assert after == before.replace('"jsonc", "lint", "pre-commit"', '"jsonc", "pre-commit"')


# The default case of each real fixture: write fixes what it may and leaves the rest.
REAL = [("credit-matrix", 0), ("jsonvet", 1), ("project-templates", 0), ("r9lab", 0), ("sourceledger", 0)]


@pytest.mark.parametrize(("repo", "exit_code"), REAL)
def test_real_fixture(repo: str, exit_code: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / repo
    shutil.copytree(FIXTURES / repo, root)
    assert _run(capsys, "write", "--root", str(root))[0] == exit_code
    after = _snapshot(root)
    assert _run(capsys, "write", "--root", str(root))[0] == exit_code
    assert _snapshot(root) == after
    assert _run(capsys, "check", "--root", str(root))[0] == exit_code


# pyproject.toml has no DOI (a gap, D2), and its name is a package id, never the reference.
@pytest.mark.parametrize(
    ("old", "new", "term"),
    [("zenodo.1234567", "zenodo.7", "identifier"), ('"name": "synthagree"', '"name": "x"', "name")],
)
def test_d2_gap_is_left_alone(
    old: str, new: str, term: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "pyproject.toml"\nwrite-manifests = "all"\n')
    codemeta = root / "codemeta.json"
    codemeta.write_text(codemeta.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")
    before = _snapshot(root)

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert _snapshot(root) == before
    *lines, _ = out.splitlines()
    assert any(line.startswith("codemeta.json") for line in lines)
    assert all(f"] {term}:" in line and line.endswith(" (edit it by hand)") for line in lines)


@pytest.mark.parametrize("bad", [".zenodo.json", "codemeta.json", "pyproject.toml"])
def test_unreadable_file_is_not_written(bad: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    shutil.copy(PLANTED / "package.json", root / "package.json")
    (root / bad).write_text("{", encoding="utf-8")
    (root / "citesync.toml").write_text('write-manifests = "all"\n', encoding="utf-8")

    code, out, err = _run(capsys, "write", "--root", str(root))
    assert (code, err) == (1, "")
    assert (root / bad).read_text(encoding="utf-8") == "{"
    assert out.splitlines()[0] == "wrote package.json"
    [line] = [line for line in out.splitlines() if "[unreadable]" in line]
    assert line.startswith(f"{bad}:1:")
    assert line.endswith(" (edit it by hand)")


def test_write_reports_as_check_does(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'write-manifests = ["keywords"]\n')
    shutil.copy(PLANTED / "pyproject.toml", root / "pyproject.toml")
    shutil.copy(PLANTED / "codemeta.json", root / "codemeta.json")

    code, out, err = _run(capsys, "write", "--root", str(root), "--format", "json")
    assert err == "wrote codemeta.json\nwrote pyproject.toml\n"
    written = json.loads(out)
    for finding in written["findings"]:
        finding["message"] = re.sub(r" \(edit it by hand.*\)$", "", finding["message"])
    check_code, check_out, _ = _run(capsys, "check", "--root", str(root), "--format", "json")
    assert (code, written) == (check_code, json.loads(check_out))
    assert code == 1


def test_an_ignored_finding_is_not_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'ignore = ["version-mismatch", "context-mismatch"]\n')
    codemeta = root / "codemeta.json"
    text = codemeta.read_text(encoding="utf-8").replace('"1.2.3"', '"2.0.0"').replace("codemeta/3.0", "codemeta/3.1")
    codemeta.write_text(text, encoding="utf-8")

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert codemeta.read_text(encoding="utf-8") == text


def _edit(path: Path, old: str, new: str) -> str:
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new), encoding="utf-8")
    return text.replace(old, new)


# source, an edit to it; the file write must leave, an edit planted in it first; the reason write gives
CANNOT = [
    *(
        ("CITATION.cff", '"Turing"', '"Turning"', name, old, new, f"renaming would drop the {what} of 'Alan Turing'")
        for name, old, new, what in [
            ("codemeta.json", '"familyName": "Turing"', '"familyName": "Turing", "email": "a@x.org"', "email"),
            (".zenodo.json", '"name": "Turing, Alan"', '"name": "Turing, Alan", "affiliation": "NPL"', "affiliation"),
            ("pyproject.toml", '{ name = "Alan Turing" }', '{ name = "Alan Turing", email = "a@x.org" }', "email"),
            ("Cargo.toml", '"Alan Turing"', '"Alan Turing <a@x.org>"', "email"),
        ]
    ),
    (
        "CITATION.cff",
        '"Lovelace"',
        '"Byron"',
        "package.json",
        '"Ada Lovelace"',
        '"Ada Lovelace (https://x.org)"',
        "renaming would drop the url of 'Ada Lovelace'",
    ),
    (
        "codemeta.json",
        '"familyName": "Turing"',
        '"familyName": "Turning"',
        "CITATION.cff",
        'family-names: "Turing"\n',
        'family-names: "Turing"\n    affiliation: "NPL"\n',
        "renaming would drop the affiliation of 'Alan Turing'",
    ),
    ("CITATION.cff", '"1.2.3"', '"1.2.3.post1"', "Cargo.toml", "", "", "semver has no spelling for 1.2.3.post1"),
    ("CITATION.cff", '"1.2.3"', '"2!1.0"', "package.json", "", "", "semver has no spelling for 2!1.0"),
    ("CITATION.cff", '"Apache-2.0"', '"MIT OR Apache-2.0"', ".zenodo.json", "", "", "Zenodo takes one licence id"),
    ("CITATION.cff", '"Apache-2.0"', '"MIT AND Apache-2.0"', ".zenodo.json", "", "", "Zenodo takes one licence id"),
    (
        "CITATION.cff",
        '"Apache-2.0"',
        '"MIT AND Apache-2.0"',
        "codemeta.json",
        "",
        "",
        "a licence list can only say OR, not AND or WITH",
    ),
    (
        "codemeta.json",
        '"https://spdx.org/licenses/Apache-2.0"',
        '"MIT AND Apache-2.0"',
        "CITATION.cff",
        "",
        "",
        "a licence list can only say OR, not AND or WITH",
    ),
]


@pytest.mark.parametrize(("source", "old", "new", "name", "planted", "plant", "reason"), CANNOT)
def test_a_value_write_cannot_spell_is_left_with_the_reason(
    source: str,
    old: str,
    new: str,
    name: str,
    planted: str,
    plant: str,
    reason: str,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _synthetic(tmp_path / "repo", f'source = "{source}"\nwrite-manifests = "all"\n')
    if planted:
        _edit(root / name, planted, plant)
    before = (root / name).read_bytes()
    _edit(root / source, old, new)

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert (root / name).read_bytes() == before
    assert any(
        line.startswith(f"{name}: ") and line.endswith(f" (edit it by hand: {reason})") for line in out.splitlines()
    ), out


@pytest.mark.parametrize("expression", ["MIT OR Apache-2.0", "(MIT OR Apache-2.0)"])
def test_an_or_licence_becomes_a_list(expression: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "pyproject.toml"\n')
    _edit(root / "pyproject.toml", '"Apache-2.0"', f'"{expression}"')
    _run(capsys, "write", "--root", str(root))
    report = json.loads(_run(capsys, "check", "--json", "--root", str(root))[1])
    assert not {f["file"] for f in report["findings"] if f["rule"] == "license-mismatch"} & {
        "CITATION.cff",
        "codemeta.json",
    }
    assert "license:\n  - MIT\n  - Apache-2.0\n" in (root / "CITATION.cff").read_text(encoding="utf-8")
    licences = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))["license"]
    assert licences == ["https://spdx.org/licenses/MIT", "https://spdx.org/licenses/Apache-2.0"]


def test_an_orcid_match_is_renamed_in_place(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'write-manifests = "all"\n')
    zenodo = _edit(
        root / ".zenodo.json", '"name": "Lovelace, Ada",', '"name": "Lovelace, Ada",\n      "affiliation": "x",'
    )
    _edit(root / "CITATION.cff", '"Lovelace"', '"Byron"')
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / ".zenodo.json").read_text(encoding="utf-8") == zenodo.replace("Lovelace, Ada", "Byron, Ada")


def _doi(n: int) -> dict[str, str]:
    return {
        "@type": "PropertyValue",
        "propertyID": "DOI",
        "value": f"10.5281/zenodo.{n}",
        "url": f"https://doi.org/10.5281/zenodo.{n}",
    }


@pytest.mark.parametrize("listed", [False, True])
def test_a_property_value_doi_keeps_its_keys(
    listed: bool,  # noqa: FBT001
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _synthetic(tmp_path / "repo")
    swhid = {"@type": "PropertyValue", "propertyID": "SWHID", "value": "swh:1:dir:0"}
    old = [swhid, _doi(1234567)] if listed else _doi(1234567)
    _edit(root / "codemeta.json", '"https://doi.org/10.5281/zenodo.1234567"', json.dumps(old))
    _edit(root / "CITATION.cff", "zenodo.1234567", "zenodo.42")

    _run(capsys, "write", "--root", str(root))
    identifier = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))["identifier"]
    assert identifier == ([swhid, _doi(42)] if listed else _doi(42))


@pytest.mark.parametrize("case_sensitive", [False, True])
def test_values_that_compare_equal_are_left_as_written(
    case_sensitive: bool,  # noqa: FBT001
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = "keywords-case-sensitive = true\n" if case_sensitive else ""
    root = _synthetic(tmp_path / "repo", config)
    codemeta = root / "codemeta.json"
    text = codemeta.read_text(encoding="utf-8")
    text = text.replace('"1.2.3"', '"v1.2.3"').replace("example/synthagree", "example/Synthagree/tree/main")
    codemeta.write_text(text.replace('"alpha", "beta", "gamma", "delta"', '"ALPHA", "beta", "gamma", "omega"'), "utf-8")

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    keywords = '"beta", "gamma", "alpha", "delta"' if case_sensitive else '"ALPHA", "beta", "gamma", "delta"'
    assert codemeta.read_text(encoding="utf-8") == text.replace('"alpha", "beta", "gamma", "delta"', keywords)


def test_write_keeps_the_file_mode(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    shutil.copy(PLANTED / "codemeta.json", root / "codemeta.json")
    (root / "codemeta.json").chmod(0o640)
    assert _run(capsys, "write", "--root", str(root))[0] == 0
    assert (root / "codemeta.json").stat().st_mode & 0o777 == 0o640
    assert sorted(p.name for p in root.iterdir()) == sorted(p.name for p in SYNTHETIC.iterdir())


def test_a_removed_author_leaves_a_multi_line_array_as_it_was(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'write-manifests = "all"\n')
    lines = [
        '    { name = "Ada Lovelace" },  # first\n',
        '    { name = "Grace Hopper" },\n',
        '    { name = "Alan Turing" },\n',
    ]
    pyproject = _edit(
        root / "pyproject.toml",
        'authors = [{ name = "Ada Lovelace" }, { name = "Alan Turing" }]',
        "authors = [\n" + "".join(lines) + "]",
    )

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "pyproject.toml").read_text(encoding="utf-8") == pyproject.replace(lines[1], "")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('"Alan"', '"Alán"'),  # a one-line splice
        ("authors:\n", 'authors:\n  - given-names: "Zoë"\n    family-names: "Hopper"\n'),  # a re-dumped list
    ],
)
def test_a_non_ascii_name_is_written_as_is(
    old: str, new: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo")
    name = re.findall(r'"(\w*[áë]\w*)"', new)[0]
    _edit(root / "CITATION.cff", old, new)

    _run(capsys, "write", "--root", str(root))
    for path in ("codemeta.json", ".zenodo.json"):
        assert name in (root / path).read_text(encoding="utf-8"), path


def test_a_symlink_target_is_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    (root / "real").mkdir()
    shutil.copy(PLANTED / "codemeta.json", root / "real" / "codemeta.json")
    (root / "codemeta.json").unlink()
    (root / "codemeta.json").symlink_to(Path("real") / "codemeta.json")

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "codemeta.json").is_symlink()
    assert (root / "real" / "codemeta.json").read_bytes() == (EXPECTED / "codemeta.json").read_bytes()


@pytest.mark.parametrize("name", NAMES)
def test_crlf_line_ends_stay(name: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    source = "codemeta.json" if name == "CITATION.cff" else "CITATION.cff"
    root = _synthetic(tmp_path / "repo", f'source = "{source}"\nwrite-manifests = "all"\n')
    (root / name).write_bytes((PLANTED / name).read_bytes().replace(b"\n", b"\r\n"))
    if name == "codemeta.json":  # a third author re-dumps the multi-line author list
        _edit(root / source, "authors:\n", 'authors:\n  - given-names: "Grace"\n    family-names: "Hopper"\n')

    assert _run(capsys, "write", "--root", str(root))[0] == 0
    written = (root / name).read_bytes()
    assert not re.search(rb"(?<!\r)\n", written)
    if name != "codemeta.json":
        assert written == _expected(name).replace(b"\n", b"\r\n")


def test_a_failed_write_changes_no_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _synthetic(tmp_path / "repo")
    for name in ("codemeta.json", ".zenodo.json"):
        shutil.copy(PLANTED / name, root / name)
    before = _snapshot(root)
    mkstemp, calls = tempfile.mkstemp, []

    def failing_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        calls.append(args)
        if len(calls) == 2:  # the second file
            raise OSError(28, "No space left on device")
        return mkstemp(*args, **kwargs)  # ty: ignore[no-matching-overload]

    monkeypatch.setattr("citesync.write.tempfile.mkstemp", failing_mkstemp)
    code, _, err = _run(capsys, "write", "--root", str(root))
    assert (code, "No space left on device" in err) == (2, True)
    assert _snapshot(root) == before


# Text edits that each plant one disagreement in the synthetic set, with the term it plants.
# .zenodo.json holds no version or DOI: as the source it leaves a gap (D2), which write never fills.
GAPS = {".zenodo.json": {"version", "identifier"}}
EDITS = [
    ("codemeta.json", '"version": "1.2.3"', '"version": "2.0.0rc1"', "version"),
    ("codemeta.json", '"familyName": "Lovelace"', '"familyName": "Byron"', "author"),
    ("codemeta.json", "codemeta/3.0", "codemeta/3.1", "@context"),
    ("codemeta.json", '"gamma", "delta"]', '"gamma", "omega"]', "keywords"),
    (".zenodo.json", '"Lovelace, Ada"', '"Lovelace, Augusta Ada"', "author"),
    (".zenodo.json", '"license": "apache-2.0"', '"license": "mit"', "license"),
    (".zenodo.json", '"title": "synthagree"', '"title": "other"', "name"),
    ("CITATION.cff", 'version: "1.2.3"', 'version: "1.3.0-beta.2"', "version"),
    ("CITATION.cff", "0000-0002-1825-0097", "0000-0001-5109-3700", "author"),
    ("CITATION.cff", '  - "delta"\n', '  - "delta"\n  - "epsilon"\n', "keywords"),
    ("CITATION.cff", 'doi: "10.5281/zenodo.1234567"', 'doi: "10.5281/zenodo.42"', "identifier"),
    ("pyproject.toml", 'license = "Apache-2.0"', 'license = "MIT OR Apache-2.0"', "license"),
    ("pyproject.toml", '{ name = "Alan Turing" }', '{ name = "Grace Hopper" }, { name = "Alan Turing" }', "author"),
    ("Cargo.toml", '"Alan Turing"', '"Alan Turing <alan@example.org>", "Grace Hopper"', "author"),
    ("Cargo.toml", 'keywords = ["alpha"', 'keywords = ["zeta", "alpha"', "keywords"),
    (
        "package.json",
        '"author": "Ada Lovelace"',
        '"author": { "name": "Ada King" }',
        "author",
    ),
    ("package.json", "example/synthagree.git", "example/synth.git", "codeRepository"),
]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    source=st.sampled_from(["CITATION.cff", "codemeta.json", ".zenodo.json"]),
    edits=st.lists(st.sampled_from(EDITS), unique=True, max_size=6),
)
def test_write_then_check_finds_nothing(
    source: str, edits: list[tuple[str, str, str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    """With a citation file as the source and every manifest field writable, write leaves nothing to report."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _synthetic(Path(tmp) / "repo", f'source = "{source}"\nwrite-manifests = "all"\n')
        for name, old, new, term in edits:
            if term in GAPS.get(source, set()):
                continue
            path = root / name
            path.write_text(path.read_text(encoding="utf-8").replace(old, new), encoding="utf-8")

        code, out, err = _run(capsys, "write", "--root", str(root))
        assert (code, err) == (0, ""), out
        after = _snapshot(root)
        assert _run(capsys, "check", "-q", "--root", str(root)) == (0, "", "")
        assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
        assert _snapshot(root) == after


ADA = "https://orcid.org/0000-0002-1825-0097"
SOFTWARE = "https://credit.niso.org/contributor-roles/software/"


def _with_roles(root: Path) -> tuple[list[object], list[object]]:
    """Add CodeMeta Role objects, as credit-matrix plans to print them, to the author and contributor lists."""
    path = root / "codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    role = {"@type": "Role", "schema:author": ADA, "roleName": SOFTWARE}
    data["author"].append(role)
    data["contributor"] = [{"@type": "Person", "givenName": "Grace", "familyName": "Hopper"}, role]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return _roles(root)


def _roles(root: Path) -> tuple[list[object], list[object]]:
    data = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
    return [a for a in data["author"] if a.get("@type") == "Role"], data["contributor"]


def test_roles_add_no_findings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    _with_roles(root)
    assert _run(capsys, "check", "-q", "--root", str(root)) == (0, "", "")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ('version: "1.2.3"', 'version: "1.2.4"'),
        ('family-names: "Turing"', 'family-names: "Turing-Smith"'),
        ('  - given-names: "Alan"\n    family-names: "Turing"\n', ""),
    ],
    ids=["version", "rename", "removal"],
)
def test_write_keeps_roles(old: str, new: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Role objects pass through a write untouched, since citesync knows no CRediT."""
    root = _synthetic(tmp_path / "repo", 'source = "CITATION.cff"\nwrite-manifests = "all"\n')
    before = _with_roles(root)
    cff = root / "CITATION.cff"
    text = cff.read_text(encoding="utf-8")
    assert old in text
    cff.write_text(text.replace(old, new), encoding="utf-8")

    code, out, err = _run(capsys, "write", "--root", str(root))
    assert (code, err) == (0, ""), out
    assert "wrote codemeta.json" in out
    assert _roles(root) == before

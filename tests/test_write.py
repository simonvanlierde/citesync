"""`citesync write` against committed expected files, plus what it must leave alone."""

import json
import os
import re
import shutil
import stat
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from citesync.cli import main
from citesync.formats import dangling_roles

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


def _findings(out: str) -> list[str]:
    """The text report's lines, less the help line under each finding."""
    return [line for line in out.splitlines() if not line.startswith("  help: ")]


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
    config = f'source = "{source}"\nwrite-manifests = "all"\ncodemeta-version = "3.0"\n'
    root = _synthetic(tmp_path / "repo", config)
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
    lines = _findings(out)[:-1]
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
    [line, _] = _findings(out)
    assert member in line
    assert line.endswith(" (edit it by hand: inherited from [workspace.package] in the workspace's Cargo.toml)")


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
    *lines, _ = _findings(out)
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
    root = _synthetic(
        tmp_path / "repo", 'ignore = ["version-mismatch", "context-mismatch"]\ncodemeta-version = "3.0"\n'
    )
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
    (  # a source author with no ORCID and a new name may be the same person, or not: neither keeps the ORCID safely
        "CITATION.cff",
        '"Lovelace"\n    orcid: "https://orcid.org/0000-0002-1825-0097"\n',
        '"Byron"\n',
        "codemeta.json",
        "",
        "",
        "renaming would drop the ORCID of 'Ada Lovelace'",
    ),
    ("CITATION.cff", '"1.2.3"', '"1.2.3.post1"', "Cargo.toml", "", "", "semver has no spelling for 1.2.3.post1"),
    ("CITATION.cff", '"1.2.3"', '"2!1.0"', "package.json", "", "", "semver has no spelling for 2!1.0"),
    ("CITATION.cff", '"1.2.3"', '"2024.10 beta"', "pyproject.toml", "", "", "2024.10 beta is not a PEP 440 version"),
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
        "CITATION.cff",
        '"Apache-2.0"',
        '"Apache-2.0 WITH LLVM-exception"',
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
        line.startswith(f"{name}:") and line.endswith(f" (edit it by hand: {reason})") for line in out.splitlines()
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


@pytest.mark.parametrize(
    ("key", "part", "family"), [("name-particle", "van", "van Lovelace"), ("name-suffix", "Jr.", "Lovelace Jr.")]
)
def test_a_given_name_rename_keeps_the_family_name_parts(
    key: str, part: str, family: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    _edit(
        root / "codemeta.json",
        '"givenName": "Ada",\n      "familyName": "Lovelace"',
        f'"givenName": "Ada K.",\n      "familyName": "{family}"',
    )
    cff = _edit(
        root / "CITATION.cff", '    family-names: "Lovelace"\n', f'    {key}: "{part}"\n    family-names: "Lovelace"\n'
    )
    _run(capsys, "write", "--root", str(root))
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == cff.replace('"Ada"', '"Ada K."')


def test_a_family_first_name_is_not_renamed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    codemeta = root / "codemeta.json"
    _edit(codemeta, '"givenName": "Ada",\n      "familyName": "Lovelace"', '"name": "Lovelace Ada"')
    _edit(
        codemeta,
        ',\n    {\n      "@type": "Person",\n      "givenName": "Alan",\n      "familyName": "Turing"\n    }',
        "",
    )
    _run(capsys, "write", "--root", str(root))
    authors = json.loads(codemeta.read_text(encoding="utf-8"))["author"]
    assert [a.get("name") or a["familyName"] for a in authors] == ["Lovelace Ada", "Turing"]


def _doi(n: int) -> dict[str, str]:
    return {
        "@type": "PropertyValue",
        "propertyID": "DOI",
        "value": f"10.5281/zenodo.{n}",
        "url": f"https://doi.org/10.5281/zenodo.{n}",
    }


@pytest.mark.parametrize("shape", ["alone", "after", "before", "record-url"])
def test_a_property_value_doi_keeps_its_keys(shape: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Only the keys holding the DOI change: a url to the Zenodo record stays, as do the list's other entries."""
    root = _synthetic(tmp_path / "repo")
    swhid = {"@type": "PropertyValue", "propertyID": "SWHID", "value": "swh:1:dir:0"}
    record = {**_doi(1234567), "url": "https://zenodo.org/records/1234567"}
    old = {
        "alone": _doi(1234567),
        "after": [swhid, _doi(1234567)],
        "before": [_doi(1234567), swhid],
        "record-url": record,
    }[shape]
    _edit(root / "codemeta.json", '"https://doi.org/10.5281/zenodo.1234567"', json.dumps(old))
    _edit(root / "CITATION.cff", "zenodo.1234567", "zenodo.42")

    _run(capsys, "write", "--root", str(root))
    identifier = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))["identifier"]
    assert (
        identifier
        == {
            "alone": _doi(42),
            "after": [swhid, _doi(42)],
            "before": [_doi(42), swhid],
            "record-url": {**record, "value": "10.5281/zenodo.42"},
        }[shape]
    )


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


@pytest.mark.parametrize("ignore", [False, True])
def test_a_near_miss_keyword_takes_the_source_spelling_in_place(
    ignore: bool,  # noqa: FBT001
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = 'write-manifests = ["keywords"]\n' + ("keywords-ignore-separators = true\n" if ignore else "")
    root = _synthetic(tmp_path / "repo", config)
    _edit(root / "CITATION.cff", '"beta"', '"big data"')
    codemeta = _edit(root / "codemeta.json", '"beta"', '"big-data"')
    pyproject = _edit(root / "pyproject.toml", '"beta"', '"big_data"')
    for name in (".zenodo.json", "package.json", "Cargo.toml"):
        _edit(root / name, '"beta"', '"big data"')

    assert _run(capsys, "write", "-q", "--root", str(root))[0] == 0
    if ignore:
        assert (root / "codemeta.json").read_text(encoding="utf-8") == codemeta
        assert (root / "pyproject.toml").read_text(encoding="utf-8") == pyproject
    else:
        assert '"keywords": ["alpha", "big data", "gamma", "delta"]' in (root / "codemeta.json").read_text("utf-8")
        assert 'keywords = ["alpha", "big data", "gamma", "delta"]' in (root / "pyproject.toml").read_text("utf-8")


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
    root = _synthetic(tmp_path / "repo", 'codemeta-version = "3.0"\n')
    (root / "real").mkdir()
    shutil.copy(PLANTED / "codemeta.json", root / "real" / "codemeta.json")
    (root / "codemeta.json").unlink()
    (root / "codemeta.json").symlink_to(Path("real") / "codemeta.json")

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "codemeta.json").is_symlink()
    assert (root / "real" / "codemeta.json").read_bytes() == (EXPECTED / "codemeta.json").read_bytes()


def test_a_symlink_out_of_the_repo_is_neither_read_nor_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\n')
    victim = tmp_path / "victim.cff"
    victim.write_bytes((root / "CITATION.cff").read_bytes().replace(b'"synthagree"', b'"secret"'))
    (root / "CITATION.cff").unlink()
    (root / "CITATION.cff").symlink_to(victim)
    before = victim.read_bytes()

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert "CITATION.cff: error[unreadable] resolves outside the repo root" in out
    assert "secret" not in out
    assert victim.read_bytes() == before


def test_a_dangling_symlink_out_of_the_repo_is_not_created(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'files = ["codemeta.json"]\n')
    (root / "codemeta.json").unlink()
    (root / "codemeta.json").symlink_to(tmp_path / "victim.json")

    code, _, err = _run(capsys, "write", "--root", str(root))
    assert (code, err) == (2, "citesync: codemeta.json: resolves outside the repo root, so write won't write it\n")
    assert not (tmp_path / "victim.json").exists()


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


@pytest.mark.parametrize("crlf_lines", [1, 12, 13])  # of 24 lines: a tie keeps LF
def test_mixed_line_ends_take_the_more_common_one(
    crlf_lines: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\n')
    lines = (PLANTED / "CITATION.cff").read_bytes().splitlines(keepends=True)
    mixed = [line.replace(b"\n", b"\r\n") for line in lines[:crlf_lines]] + lines[crlf_lines:]
    (root / "CITATION.cff").write_bytes(b"".join(mixed))

    assert _run(capsys, "write", "--root", str(root))[0] == 0
    expected = _expected("CITATION.cff")
    assert (root / "CITATION.cff").read_bytes() == (expected.replace(b"\n", b"\r\n") if crlf_lines > 12 else expected)


def test_a_mixed_file_write_leaves_alone_keeps_its_line_ends(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    _edit(root / "codemeta.json", '"https://spdx.org/licenses/Apache-2.0"', '"MIT AND Apache-2.0"')
    cff = root / "CITATION.cff"
    cff.write_bytes(cff.read_bytes().replace(b"\n", b"\r\n", 1))
    before = cff.read_bytes()
    assert _run(capsys, "write", "--root", str(root))[0] == 1
    assert cff.read_bytes() == before


def test_a_failed_write_changes_no_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _synthetic(tmp_path / "repo")
    for name in ("codemeta.json", ".zenodo.json"):
        shutil.copy(PLANTED / name, root / name)
    before = _snapshot(root)
    mkstemp, calls = tempfile.mkstemp, []

    def failing_mkstemp(*args: object, **kwargs: object) -> tuple[int, str]:
        calls.append(kwargs)
        if len(calls) == 2:  # the second file
            raise OSError(28, "No space left on device")
        return mkstemp(*args, **kwargs)  # ty: ignore[no-matching-overload]

    monkeypatch.setattr("citesync.write.tempfile.mkstemp", failing_mkstemp)
    code, _, err = _run(capsys, "write", "--root", str(root))
    assert (code, "No space left on device" in err) == (2, True)
    assert _snapshot(root) == before
    # beside its file, so the move is a rename on one file system, and hidden
    assert calls[0] == {"dir": root, "prefix": ".codemeta.json.", "suffix": ".tmp"}


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


def test_replacing_the_person_of_a_role_warns(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Write replaces the first author with another ORCID, dropping the one both Roles name; check then warns."""
    root = _synthetic(tmp_path / "repo", 'source = "CITATION.cff"\nwrite-manifests = "all"\n')
    before = _with_roles(root)
    cff = root / "CITATION.cff"
    old = '  - given-names: "Ada"\n    family-names: "Lovelace"\n    orcid: "https://orcid.org/0000-0002-1825-0097"\n'
    new = '  - given-names: "Grace"\n    family-names: "Hopper"\n    orcid: "https://orcid.org/0000-0001-5109-3700"\n'
    cff.write_text(cff.read_text(encoding="utf-8").replace(old, new))

    code, out, err = _run(capsys, "write", "--root", str(root))
    assert (code, err) == (0, ""), out
    assert _roles(root) == before

    code, out, _ = _run(capsys, "check", "--root", str(root), "--format", "json")
    found = [(f["rule"], f["severity"], f["file"], f["term"]) for f in json.loads(out)["findings"]]
    assert code == 0
    assert [f for f in found if f[1] != "info"] == [
        ("role-dangling", "warning", "codemeta.json", "author"),
        ("role-dangling", "warning", "codemeta.json", "contributor"),
    ]


def test_dangling_roles() -> None:
    other, third = "https://orcid.org/0000-0001-5109-3700", "https://orcid.org/0000-0002-9079-593X"
    data = {
        "author": [
            {"@type": "Person", "@id": ADA},
            {"@type": "Role", "schema:author": {"@id": "http://orcid.org/0000-0002-1825-0097"}},
            {"@type": "Role", "schema:author": other},
            {"@type": "Role", "roleName": SOFTWARE},
        ],
        "contributor": {"@type": "Role", "schema:author": third},
    }
    assert dangling_roles(data) == (("author", "0000-0001-5109-3700"), ("contributor", "0000-0002-9079-593X"))


def test_dangling_roles_read_the_type_and_id_aliases() -> None:
    """CodeMeta 3's context makes `type` and `id` aliases of `@type` and `@id`; credit-matrix writes Roles that way."""
    other = "https://orcid.org/0000-0001-5109-3700"
    data = {
        "author": [
            {"type": "Person", "id": ADA, "givenName": "Ada", "familyName": "Lovelace"},
            {"type": "Role", "schema:author": ADA, "roleName": SOFTWARE},
            {"type": "Role", "schema:author": {"id": other}, "roleName": SOFTWARE},
        ]
    }
    assert dangling_roles(data) == (("author", "0000-0001-5109-3700"),)


def test_an_organization_typed_by_alias_is_written_as_an_entity(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    path = root / "codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["author"].append({"type": "Organization", "name": "Example Lab"})
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    _run(capsys, "write", "--root", str(root))
    cff = (root / "CITATION.cff").read_text(encoding="utf-8")
    assert '    family-names: "Turing"\n  - name: Example Lab\n' in cff


def test_role_dangling_lists_the_orcids_per_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    path = root / "codemeta.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = ["0000-0001-5109-3700", "0000-0002-9079-593X", "0000-0003-1419-2405"]
    roles = [{"@type": "Role", "schema:author": f"https://orcid.org/{i}", "roleName": SOFTWARE} for i in ids]
    data["author"] += roles[:2]
    data["contributor"] = roles[2:]
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    code, out, _ = _run(capsys, "check", "--root", str(root), "--format", "json")
    found = [(f["term"], f["message"]) for f in json.loads(out)["findings"] if f["rule"] == "role-dangling"]
    assert code == 0
    tail = "which no Person in author or contributor has"
    assert found == [
        ("author", f"a Role points at {ids[0]}, {ids[1]}, {tail}"),
        ("contributor", f"a Role points at {ids[2]}, {tail}"),
    ]


def test_diff_prints_the_edit_and_writes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    cff = root / "CITATION.cff"
    cff.write_text(cff.read_text(encoding="utf-8").replace('version: "1.2.3"', 'version: "1.2.4"'), encoding="utf-8")
    before = _snapshot(root)

    code, out, err = _run(capsys, "write", "--diff", "--root", str(root))
    assert (code, err) == (1, "would fix 1 finding in 1 file\n")
    assert _snapshot(root) == before
    files = [line for line in out.splitlines() if line.startswith(("--- ", "+++ "))]
    assert files == [
        "--- a/codemeta.json",
        "+++ b/codemeta.json",
    ]  # .zenodo.json has no version, manifests aren't opted in
    changed = [line for line in out.splitlines() if line[:1] in "+-" and line[:3] not in {"---", "+++"}]
    assert changed == ['-  "version": "1.2.3",', '+  "version": "1.2.4",']

    _run(capsys, "write", "-q", "--root", str(root))
    assert _run(capsys, "write", "--diff", "--root", str(root)) == (
        0,
        "",
        "",
    )  # manifest errors remain, nothing to write


def test_diff_shows_a_codemeta_json_write_would_create(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'files = ["codemeta.json"]\n')
    (root / "codemeta.json").unlink()

    code, out, err = _run(capsys, "write", "--diff", "--root", str(root))
    assert (code, err) == (1, "would fix 1 finding in 1 file\n")
    assert out.splitlines()[:2] == ["--- /dev/null", "+++ b/codemeta.json"]
    assert not (root / "codemeta.json").exists()


def test_diff_takes_no_format(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["write", "--diff", "--format", "json"])
    assert exc.value.code == 2
    assert "--diff" in capsys.readouterr().err


def _with_organization(root: Path) -> None:
    """Add The Synth Team as a third author to the three citation files, each in its own spelling."""
    _edit(
        root / "CITATION.cff",
        '    family-names: "Turing"\n',
        '    family-names: "Turing"\n  - name: "The Synth Team"\n',
    )
    data = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
    data["author"].append({"@type": "Organization", "name": "The Synth Team"})
    (root / "codemeta.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _edit(
        root / ".zenodo.json",
        '"name": "Turing, Alan"\n    }',
        '"name": "Turing, Alan"\n    },\n    {\n      "name": "The Synth Team"\n    }',
    )


@pytest.mark.parametrize("source", ["CITATION.cff", "codemeta.json", ".zenodo.json"])
def test_an_organization_author_is_kept(source: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A codemeta.json author with only a `name`, such as an Organization, reads as CFF's entity `name` does."""
    root = _synthetic(tmp_path / "repo", f'source = "{source}"\nmanifests = []\n')
    _with_organization(root)
    before = _snapshot(root)

    assert _run(capsys, "check", "-q", "--root", str(root)) == (0, "", "")
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert _snapshot(root) == before


def test_diff_reports_an_unreadable_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """--diff fails on a file it can't read, as `ruff format --diff` does, so a CI gate never passes a broken repo."""
    root = _synthetic(tmp_path / "repo")
    (root / ".zenodo.json").write_text('{"title": ', encoding="utf-8")

    code, out, err = _run(capsys, "write", "--diff", "--root", str(root))
    assert (code, out) == (1, "")
    assert "error[unreadable]" in err


@pytest.mark.parametrize("source", ["CITATION.cff", "Cargo.toml"])
def test_cargo_keywords_keep_their_hyphens(source: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # crates.io refuses a keyword with a space, so a hyphenated Cargo.toml keyword matches a spaced one.
    root = _synthetic(tmp_path / "repo", f'source = "{source}"\nwrite-manifests = ["keywords"]\n')
    for name in ("CITATION.cff", "codemeta.json", ".zenodo.json", "pyproject.toml", "package.json"):
        _edit(root / name, '"beta"', '"big data"')
    cargo = _edit(root / "Cargo.toml", '"beta"', '"big-data"')
    cff = (root / "CITATION.cff").read_text(encoding="utf-8")

    assert _run(capsys, "check", "-q", "--root", str(root))[0] == 0
    assert _run(capsys, "write", "-q", "--root", str(root))[0] == 0
    assert (root / "Cargo.toml").read_text(encoding="utf-8") == cargo

    # one more word makes the files disagree, so write edits them; the hyphen and the space both stay
    _edit(root / "Cargo.toml", '"delta"]', '"delta", "zeta"]')
    _run(capsys, "write", "-q", "--root", str(root))
    if source == "Cargo.toml":
        assert (root / "CITATION.cff").read_text(encoding="utf-8") == cff + '  - "zeta"\n'
    else:
        assert (root / "Cargo.toml").read_text(encoding="utf-8") == cargo


def test_a_cff_entity_is_written_as_an_organization(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'write-manifests = "all"\n')
    _edit(
        root / "CITATION.cff", '    family-names: "Turing"\n', '    family-names: "Turing"\n  - name: "Example Lab"\n'
    )

    _run(capsys, "write", "--root", str(root))
    codemeta = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
    assert codemeta["author"][-1] == {"@type": "Organization", "name": "Example Lab"}
    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    assert zenodo["creators"][-1] == {"name": "Example Lab"}
    assert _run(capsys, "check", "--root", str(root))[0] == 0


def test_a_grown_json_array_keeps_its_one_line_elements(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    one_line = (
        '  "author": [\n'
        '    {"@type": "Person", "@id": "https://orcid.org/0000-0002-1825-0097", '
        '"givenName": "Ada", "familyName": "Lovelace"},\n'
        '    {"@type": "Person", "givenName": "Alan", "familyName": "Turing"}\n'
        "  ],\n"
    )
    text = (root / "codemeta.json").read_text(encoding="utf-8")
    multi = text[text.index('  "author": [') : text.index('  "keywords"')]
    codemeta = _edit(root / "codemeta.json", multi, one_line)
    _edit(
        root / "CITATION.cff",
        '    family-names: "Turing"\n',
        '    family-names: "Turing"\n  - given-names: "Grace"\n    family-names: "Hopper"\n',
    )

    _run(capsys, "write", "--root", str(root))
    turing = '{"@type": "Person", "givenName": "Alan", "familyName": "Turing"}'
    hopper = '{"@type": "Person", "givenName": "Grace", "familyName": "Hopper"}'
    assert (root / "codemeta.json").read_text(encoding="utf-8") == codemeta.replace(turing, f"{turing},\n    {hopper}")


# What write creates from the synthetic CITATION.cff: no contributor, since CFF has no contributor list.
CREATED = """{
  "@context": "https://w3id.org/codemeta/3.0",
  "@type": "SoftwareSourceCode",
  "name": "synthagree",
  "description": "A made-up package whose metadata files all agree.",
  "version": "1.2.3",
  "datePublished": "2026-01-15",
  "identifier": "https://doi.org/10.5281/zenodo.1234567",
  "codeRepository": "https://github.com/example/synthagree",
  "license": "https://spdx.org/licenses/Apache-2.0",
  "author": [
    {
      "@type": "Person",
      "givenName": "Ada",
      "familyName": "Lovelace",
      "@id": "https://orcid.org/0000-0002-1825-0097"
    },
    {
      "@type": "Person",
      "givenName": "Alan",
      "familyName": "Turing"
    }
  ],
  "keywords": [
    "alpha",
    "beta",
    "gamma",
    "delta"
  ]
}
"""


@pytest.mark.parametrize("rel", ["codemeta.json", "docs/codemeta.json", "docs/meta/codemeta.json"])
def test_a_listed_codemeta_json_that_is_missing_is_created(
    rel: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", f'files = ["{rel}", ".zenodo.json"]\n')
    (root / "codemeta.json").unlink()

    code, out, _ = _run(capsys, "check", "--root", str(root))
    assert code == 1
    assert f"{rel}: error[file-missing] listed under files" in out
    umask = os.umask(0o022)
    try:
        assert _run(capsys, "write", "--root", str(root))[1].startswith(f"wrote {rel}\n")
    finally:
        os.umask(umask)
    assert (root / rel).read_text(encoding="utf-8") == CREATED
    assert stat.S_IMODE((root / rel).stat().st_mode) == 0o644, "what open() would give a new file"
    assert _run(capsys, "check", "--root", str(root))[0] == 0


@pytest.mark.parametrize(
    ("config", "cff", "code"),
    [('ignore = ["file-missing"]\n', None, 0), ("", "title: [\n", 1)],
    ids=["ignored", "unreadable-source"],
)
def test_a_missing_codemeta_json_is_not_created(
    config: str, cff: str | None, code: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'files = ["codemeta.json"]\n' + config)
    (root / "codemeta.json").unlink()
    if cff:
        (root / "CITATION.cff").write_text(cff, encoding="utf-8")
    assert _run(capsys, "write", "-q", "--root", str(root))[0] == code
    assert not (root / "codemeta.json").exists()


def test_a_created_codemeta_json_leaves_out_what_it_cannot_spell(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'files = ["codemeta.json"]\nmanifests = []\n')
    (root / "codemeta.json").unlink()
    _edit(root / "CITATION.cff", 'license: "Apache-2.0"', 'license: "MIT AND Apache-2.0"')
    _edit(root / "CITATION.cff", "date-released: 2026-01-15", 'date-released: "2026"')

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 0
    assert out.splitlines()[0] == (
        "wrote codemeta.json, leaving out datePublished: 2026 is not a YYYY-MM-DD date;"
        " license: a licence list can only say OR, not AND or WITH"
    )
    created = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
    assert {"license", "datePublished"} & created.keys() == set()


def test_codemeta_version_sets_a_created_codemeta_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Unset, it is 3.0, as CREATED shows."""
    root = _synthetic(tmp_path / "repo", 'files = ["codemeta.json"]\ncodemeta-version = "4.0"\n')
    (root / "codemeta.json").unlink()
    _run(capsys, "write", "--root", str(root))
    created = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
    assert created["@context"] == "https://w3id.org/codemeta/4.0"


def test_any_codemeta_version_passes_and_stays_when_unset(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo")
    _edit(root / "codemeta.json", "codemeta/3.0", "codemeta/4.0")
    before = _snapshot(root)
    assert "context-mismatch" not in _run(capsys, "check", "--root", str(root))[1]
    _run(capsys, "write", "--root", str(root))
    assert (root / "codemeta.json").read_bytes() == before["codemeta.json"]


def test_a_missing_zenodo_json_is_reported_not_created(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'files = ["codemeta.json", ".zenodo.json"]\n')
    (root / ".zenodo.json").unlink()

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert ".zenodo.json: error[file-missing]" in out
    assert not (root / ".zenodo.json").exists()


def test_a_date_cff_cannot_hold_is_left_for_a_hand_edit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\n')
    codemeta = root / "codemeta.json"
    codemeta.write_text(codemeta.read_text().replace('"2026-01-15"', '"January 2026"'), encoding="utf-8")
    before = _snapshot(root)
    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert "January 2026 is not a YYYY-MM-DD date" in out
    assert _snapshot(root) == before


def _contributors(root: Path, codemeta: list[dict], zenodo: list[dict]) -> None:
    for name, key, people in (("codemeta.json", "contributor", codemeta), (".zenodo.json", "contributors", zenodo)):
        data = json.loads((root / name).read_text(encoding="utf-8"))
        data[key] = people
        (root / name).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


ORCID = "0000-0002-1825-0097"


def test_a_zenodo_contributor_is_renamed_by_orcid_and_keeps_its_type(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\n')
    person = {"@type": "Person", "@id": f"https://orcid.org/{ORCID}", "givenName": "Grace", "familyName": "Hopper"}
    _contributors(root, [person], [{"name": "Hopper, G.", "orcid": ORCID, "type": "Editor"}])
    assert _run(capsys, "write", "--root", str(root))[0] == 0
    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    assert zenodo["contributors"] == [{"name": "Hopper, Grace", "orcid": ORCID, "type": "Editor"}]


def test_a_new_zenodo_contributor_is_left_for_a_hand_edit(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\n')
    grace = {"@type": "Person", "givenName": "Grace", "familyName": "Hopper"}
    ada = {"@type": "Person", "givenName": "Ada", "familyName": "Byron"}
    _contributors(root, [grace, ada], [{"name": "Hopper, Grace", "type": "Other"}])
    before = (root / ".zenodo.json").read_bytes()
    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert "(edit it by hand: Zenodo needs a type for each contributor, which citesync doesn't choose)" in out
    assert (root / ".zenodo.json").read_bytes() == before


def test_comments_above_a_document_start_survive(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    cff = _edit(root / "CITATION.cff", "cff-version", "\n---\n# under the marker\ncff-version")
    _edit(root / "codemeta.json", '"1.2.3"', '"1.2.4"')
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == cff.replace('"1.2.3"', '"1.2.4"')


LONG = "A made-up package whose metadata files all agree, described at more length than a YAML line wraps at."
CFF_LAYOUT = """cff-version: 1.2.0
message: "If you use this software, please cite it as below."
title: "synthagree"
abstract: "A made-up package whose metadata files all agree."
version: "1.2.3"
authors:
{d}given-names: "Ada"
{c}family-names: "Lovelace"
{c}orcid: "https://orcid.org/0000-0002-1825-0097"
{d}given-names: "Alan"
{c}family-names: "Turing"
preferred-citation:
{m}type: software
{m}title: "synthagree"
{m}authors:
{m}{d}name: "The Synth Team"
"""


@pytest.mark.parametrize(
    ("dash", "under", "nest"),
    [("  - ", "    ", "  "), ("- ", "  ", "  "), ("  -   ", "      ", "    "), ("-  ", "   ", "   ")],
    ids=["indented", "flush", "wide", "three"],
)
def test_a_cff_keeps_its_indentation_and_long_lines(
    dash: str, under: str, nest: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(
        tmp_path / "repo", 'source = "codemeta.json"\nfiles = ["CITATION.cff", "codemeta.json"]\nmanifests = []\n'
    )
    cff = CFF_LAYOUT.format(d=dash, c=under, m=nest)
    (root / "CITATION.cff").write_text(cff, encoding="utf-8")
    _edit(root / "codemeta.json", '"1.2.3"', '"1.2.4"')
    _edit(root / "codemeta.json", '"A made-up package whose metadata files all agree."', f'"{LONG}"')
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    expected = cff.replace('"1.2.3"', '"1.2.4"').replace("A made-up package whose metadata files all agree.", LONG)
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == expected


def test_a_person_with_only_an_orcid_is_left_out_of_a_manifest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nwrite-manifests = "all"\n')
    _edit(
        root / "codemeta.json",
        '"givenName": "Alan",\n      "familyName": "Turing"',
        '"@id": "https://orcid.org/0000-0001-5109-3700"',
    )
    before = {name: (root / name).read_bytes() for name in ("Cargo.toml", "pyproject.toml")}

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert {name: (root / name).read_bytes() for name in before} == before
    reason = "(edit it by hand: 0000-0001-5109-3700 has no name, and this file has no place for an ORCID)"
    assert sorted(line.split(":")[0] for line in out.splitlines() if line.endswith(reason)) == list(before)
    cff = (root / "CITATION.cff").read_text(encoding="utf-8")
    assert (
        '    orcid: "https://orcid.org/0000-0002-1825-0097"\n  - orcid: "https://orcid.org/0000-0001-5109-3700"\n'
        in cff
    )


def test_a_package_json_gets_only_the_first_author(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A package.json has one author: with two in the source, the first is written and the second isn't added."""
    root = _synthetic(tmp_path / "repo", 'write-manifests = "all"\n')
    package = _edit(root / "package.json", '"author": "Ada Lovelace"', '"author": "Marie Curie"')
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "package.json").read_text(encoding="utf-8") == package.replace("Marie Curie", "Ada Lovelace")


def test_a_package_json_source_moves_its_author_first_and_keeps_the_rest(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "package.json"\nmanifests = ["package.json"]\n')
    _edit(root / "package.json", '"author": "Ada Lovelace"', '"author": "Marie Curie <marie@example.org>"')
    turing = '  - given-names: "Alan"\n    family-names: "Turing"\n    affiliation: "NPL"\n'
    curie = '  - given-names: "Marie"\n    family-names: "Curie"\n'
    cff = _edit(root / "CITATION.cff", '  - given-names: "Alan"\n    family-names: "Turing"\n', turing + curie)
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    expected = cff.replace(turing + curie, turing).replace("authors:\n", "authors:\n" + curie)
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == expected


def test_a_three_word_name_splits_at_the_last_space(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "package.json"\nmanifests = ["package.json"]\n')
    _edit(root / "package.json", '"Ada Lovelace"', '"Marie Skłodowska Curie"')
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    cff = (root / "CITATION.cff").read_text(encoding="utf-8")
    assert 'authors:\n  - given-names: "Marie Skłodowska"\n    family-names: "Curie"\n  - given-names: "Ada"\n' in cff
    zenodo = json.loads((root / ".zenodo.json").read_text(encoding="utf-8"))
    assert zenodo["creators"][0] == {"name": "Curie, Marie Skłodowska"}


def test_a_name_only_codemeta_entry_is_renamed_in_its_one_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Its ORCID keeps its spelling, and a name-only entry the source dropped goes without a complaint."""
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    codemeta = _edit(
        root / "codemeta.json",
        '"@id": "https://orcid.org/0000-0002-1825-0097",\n      "givenName": "Ada",\n      "familyName": "Lovelace"',
        '"@id": "http://orcid.org/0000-0002-1825-0097",\n      "name": "Ada Lovelace"',
    )
    codemeta = _edit(
        root / "codemeta.json", '"givenName": "Alan",\n      "familyName": "Turing"', '"name": "Alan Turing"'
    )
    _edit(root / "CITATION.cff", '"Lovelace"', '"Byron"')
    _edit(root / "CITATION.cff", '  - given-names: "Alan"\n    family-names: "Turing"\n', "")

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    alan = ',\n    {\n      "@type": "Person",\n      "name": "Alan Turing"\n    }'
    expected = codemeta.replace('"name": "Ada Lovelace"', '"name": "Ada Byron"').replace(alan, "")
    assert (root / "codemeta.json").read_text(encoding="utf-8") == expected


def test_a_changed_orcid_is_written_in_each_files_form(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """Zenodo takes a bare ORCID, CITATION.cff a URL in the quotes it had."""
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    _edit(root / "codemeta.json", "0000-0002-1825-0097", "0000-0001-5109-3700")
    cff = (root / "CITATION.cff").read_text(encoding="utf-8")
    zenodo = (root / ".zenodo.json").read_text(encoding="utf-8")

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == cff.replace(
        "0000-0002-1825-0097", "0000-0001-5109-3700"
    )
    assert (root / ".zenodo.json").read_text(encoding="utf-8") == zenodo.replace(
        '"orcid": "0000-0002-1825-0097"', '"orcid": "0000-0001-5109-3700"'
    )


OLD_ADA = '  - given-names: "Ada"\n    name-particle: "de"\n    family-names: "Lovelace"\n    name-suffix: "II"\n'


@pytest.mark.parametrize(
    ("codemeta_ada", "cff_ada"),
    [
        ('"givenName": "Ada",\n      "familyName": "Byron"', '  - given-names: "Ada"\n    family-names: "Byron"\n'),
        ('"familyName": "de Lovelace II"', OLD_ADA.replace('given-names: "Ada"\n    ', "")),
    ],
    ids=["new-family-name", "no-given-name"],
)
def test_a_cff_rename_by_orcid_rewrites_the_name_parts(
    codemeta_ada: str, cff_ada: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A new family name replaces the particle and suffix; the same one with no given name only drops given-names."""
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    _edit(root / "CITATION.cff", '  - given-names: "Ada"\n    family-names: "Lovelace"\n', OLD_ADA)
    cff = _edit(
        root / "CITATION.cff",
        '  - given-names: "Alan"\n    family-names: "Turing"\n',
        '  - family-names: "Tu"\n    orcid: "http://orcid.org/0000-0001-5109-3700"\n',  # a match keeps its spelling
    )
    _edit(root / "codemeta.json", '"givenName": "Ada",\n      "familyName": "Lovelace"', codemeta_ada)
    _edit(
        root / "codemeta.json",
        '"givenName": "Alan",\n      "familyName": "Turing"',
        '"@id": "https://orcid.org/0000-0001-5109-3700",\n      "familyName": "Tu Youyou"',
    )

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    expected = cff.replace(OLD_ADA, cff_ada).replace('"Tu"', '"Tu Youyou"')
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == expected


# given, family, ORCID: a small pool, so the draws share people, ORCIDs and names
POOL = [
    ("Ada", "Lovelace", "0000-0002-1825-0097"),
    ("Alan", "Turing", "0000-0001-5109-3700"),
    ("Marie", "Curie", "0000-0002-9079-593X"),
    ("Grace", "Hopper", "0000-0003-1419-2405"),
    ("Youyou", "Tu", None),
]
Drawn = list[tuple[int, bool, bool]]
PEOPLE = st.lists(st.tuples(st.sampled_from(range(len(POOL))), st.booleans(), st.booleans()), min_size=1, max_size=4)


def _cff_authors(people: Drawn) -> str:
    lines = []
    for i, orcid, extra in people:
        given, family, number = POOL[i]
        lines += [f'  - given-names: "{given}"', f'    family-names: "{family}"']
        lines += [f'    orcid: "https://orcid.org/{number}"'] if orcid and number else []
        lines += ['    affiliation: "Example Lab"'] if extra else []
    return "\n".join(lines) + "\n"


def _codemeta_authors(people: Drawn) -> list[dict[str, str]]:
    out = []
    for i, orcid, extra in people:
        given, family, number = POOL[i]
        out.append(
            {"@type": "Person"}
            | ({"@id": f"https://orcid.org/{number}"} if orcid and number else {})
            | {"givenName": given, "familyName": family}
            | ({"email": f"{given.lower()}@example.org"} if extra else {})
        )
    return out


def _zenodo_creators(people: Drawn) -> list[dict[str, str]]:
    out = []
    for i, orcid, extra in people:
        given, family, number = POOL[i]
        out.append(
            {"name": f"{family}, {given}"}
            | ({"orcid": number} if orcid and number else {})
            | ({"affiliation": "Example Lab"} if extra else {})
        )
    return out


@settings(max_examples=40, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(source=PEOPLE, codemeta=PEOPLE, zenodo=PEOPLE)
def test_write_settles_any_author_lists(
    source: Drawn, codemeta: Drawn, zenodo: Drawn, capsys: pytest.CaptureFixture[str]
) -> None:
    """After write, every author finding left is one write gave a reason for, and a second write changes nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        root = _synthetic(Path(tmp) / "repo", "manifests = []\n")
        cff = (root / "CITATION.cff").read_text(encoding="utf-8")
        start, end = cff.index("authors:\n") + len("authors:\n"), cff.index("doi:")
        (root / "CITATION.cff").write_text(cff[:start] + _cff_authors(source) + cff[end:], encoding="utf-8")
        for name, key, people in (
            ("codemeta.json", "author", _codemeta_authors(codemeta)),
            (".zenodo.json", "creators", _zenodo_creators(zenodo)),
        ):
            data = json.loads((root / name).read_text(encoding="utf-8"))
            data[key] = people
            (root / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

        _, out, err = _run(capsys, "write", "--root", str(root))
        assert err == ""
        left = [line for line in out.splitlines() if ": error[" in line]
        assert all("(edit it by hand: " in line for line in left), out
        after = _snapshot(root)
        _run(capsys, "write", "--root", str(root))
        assert _snapshot(root) == after


def test_a_cff_author_list_led_by_a_bare_string_still_grows(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A string isn't a CFF person: it goes to the end, and the new entry takes no quotes from it."""
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    cff = _edit(root / "CITATION.cff", "authors:\n", 'authors:\n  - "The Synth Team"\n')
    _edit(
        root / "codemeta.json",
        '"familyName": "Turing"\n    }',
        '"familyName": "Turing"\n    },\n    {"@type": "Person", "givenName": "Grace", "familyName": "Hopper"}',
    )
    _run(capsys, "write", "-q", "--root", str(root))
    turing = '    family-names: "Turing"\n'
    expected = cff.replace('  - "The Synth Team"\n', "").replace(
        turing, turing + '  - given-names: Grace\n    family-names: Hopper\n  - "The Synth Team"\n'
    )
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == expected


def test_a_dropped_author_may_have_name_parts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    turing = '    family-names: "Turing"\n'
    cff = _edit(
        root / "CITATION.cff",
        turing,
        turing
        + '  - given-names: "Marie"\n    name-particle: "de"\n    family-names: "Curie"\n    name-suffix: "II"\n',
    )
    assert cff != SYNTHETIC.joinpath("CITATION.cff").read_text(encoding="utf-8")
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "CITATION.cff").read_bytes() == (SYNTHETIC / "CITATION.cff").read_bytes()


def test_a_dropped_entry_with_only_an_orcid_and_more_is_named_by_what_it_holds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    data = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
    extra = {"@type": "Person", "@id": "https://orcid.org/0000-0002-9079-593X", "email": "someone@example.org"}
    data["author"].append(extra)
    (root / "codemeta.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert f"(edit it by hand: renaming would drop the email of {extra!r})" in out


def test_a_second_person_of_the_same_name_is_a_new_entry(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    turing = '    family-names: "Turing"\n'
    _edit(root / "CITATION.cff", turing, turing + '  - given-names: "Alan"\n' + turing)
    codemeta = _edit(
        root / "codemeta.json", '"familyName": "Turing"', '"familyName": "Turing",\n      "email": "alan@example.org"'
    )
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    alan = '\n    {\n      "@type": "Person",\n      "givenName": "Alan",\n      "familyName": "Turing"\n    }'
    with_email = '"email": "alan@example.org"\n    }'
    assert (root / "codemeta.json").read_text(encoding="utf-8") == codemeta.replace(with_email, with_email + "," + alan)


@pytest.mark.parametrize("authors", [1, 2])
def test_a_single_codemeta_author_node_stays_one_node_while_it_can(
    authors: int, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """JSON-LD allows one node for a list of one; a second author makes it a list."""
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    data = json.loads((root / "codemeta.json").read_text(encoding="utf-8"))
    ada, alan = data["author"]
    data["author"] = ada
    (root / "codemeta.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    _edit(root / "CITATION.cff", '"Lovelace"', '"Byron"')
    if authors == 1:
        _edit(root / "CITATION.cff", '  - given-names: "Alan"\n    family-names: "Turing"\n', "")
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    byron = {**ada, "familyName": "Byron"}
    assert json.loads((root / "codemeta.json").read_text(encoding="utf-8"))["author"] == (
        byron if authors == 1 else [byron, alan]
    )


def test_a_manifest_source_only_adds_keywords_to_the_citation_files(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A manifest's keywords need only be among a citation file's, so the citation files keep their extras."""
    root = _synthetic(tmp_path / "repo", 'source = "pyproject.toml"\nmanifests = ["pyproject.toml"]\n')
    _edit(root / "pyproject.toml", '"alpha", "beta", "gamma", "delta"', '"alpha", "beta", "zeta"')
    codemeta = (root / "codemeta.json").read_text(encoding="utf-8")
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "codemeta.json").read_text(encoding="utf-8") == codemeta.replace('"delta"]', '"delta", "zeta"]')


def test_a_near_miss_beside_its_own_spelling_is_dropped_not_doubled(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    _edit(root / "CITATION.cff", '  - "beta"\n', '  - "beta"\n  - "foo bar"\n')
    codemeta = _edit(
        root / "codemeta.json", '"alpha", "beta", "gamma", "delta"', '"alpha", "foo-bar", "beta", "foo bar"'
    )
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    expected = codemeta.replace('"alpha", "foo-bar", "beta", "foo bar"', '"alpha", "beta", "foo bar", "gamma", "delta"')
    assert (root / "codemeta.json").read_text(encoding="utf-8") == expected


def test_a_near_miss_in_cff_keeps_its_quotes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "codemeta.json"\nmanifests = []\n')
    _edit(root / "codemeta.json", '"beta"', '"big data"')
    cff = _edit(root / "CITATION.cff", '"beta"', '"big-data"')
    _run(capsys, "write", "-q", "--root", str(root))
    assert (root / "CITATION.cff").read_text(encoding="utf-8") == cff.replace('"big-data"', '"big data"')


def test_a_codemeta_keyword_string_becomes_a_list(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    codemeta = _edit(root / "codemeta.json", '["alpha", "beta", "gamma", "delta"]', '"alpha, beta, gamma"')
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    expected = codemeta.replace('"alpha, beta, gamma"', '["alpha", "beta", "gamma", "delta"]')
    assert (root / "codemeta.json").read_text(encoding="utf-8") == expected


def test_a_legacy_licence_table_is_edited_in_place(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'write-manifests = ["license"]\n')
    pyproject = _edit(root / "pyproject.toml", 'license = "Apache-2.0"', 'license = { text = "MIT" }')
    assert _run(capsys, "write", "-q", "--root", str(root))[0] == 0
    assert (root / "pyproject.toml").read_text(encoding="utf-8") == pyproject.replace('"MIT"', '"Apache-2.0"')


def test_a_codemeta_licence_list_keeps_its_url_form(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    codemeta = _edit(
        root / "codemeta.json", '"https://spdx.org/licenses/Apache-2.0"', '["https://spdx.org/licenses/MIT"]'
    )
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    expected = codemeta.replace('["https://spdx.org/licenses/MIT"]', '["https://spdx.org/licenses/Apache-2.0"]')
    assert (root / "codemeta.json").read_text(encoding="utf-8") == expected


@pytest.mark.parametrize("listed", [False, True])
def test_codemeta_version_sets_the_context(
    listed: bool,  # noqa: FBT001
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = _synthetic(tmp_path / "repo", 'codemeta-version = "3.0"\nmanifests = []\n')
    old = ["https://w3id.org/codemeta/3.1", "https://schema.org"] if listed else "https://w3id.org/codemeta/3.1"
    codemeta = _edit(root / "codemeta.json", '"https://w3id.org/codemeta/3.0"', json.dumps(old))
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert (root / "codemeta.json").read_text(encoding="utf-8") == codemeta.replace("codemeta/3.1", "codemeta/3.0")


def test_a_value_left_for_a_hand_edit_still_lets_the_next_be_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", "manifests = []\n")
    _edit(root / "CITATION.cff", 'license: "Apache-2.0"', 'license: "MIT OR Apache-2.0"')
    _edit(root / "CITATION.cff", '  - "delta"\n', '  - "delta"\n  - "epsilon"\n')
    zenodo = (root / ".zenodo.json").read_text(encoding="utf-8")
    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert ".zenodo.json:21:3: error[license-mismatch]" in out
    assert (root / ".zenodo.json").read_text(encoding="utf-8") == zenodo.replace('"delta"]', '"delta", "epsilon"]')


def test_a_cargo_member_writes_its_own_keys_past_an_inherited_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "jsonvet"
    shutil.copytree(FIXTURES / "jsonvet", root)
    member = "crates/jsonvet/Cargo.toml"
    (root / "citesync.toml").write_text(f'manifests = ["{member}"]\nwrite-manifests = "all"\n', encoding="utf-8")
    _edit(root / "CITATION.cff", 'license: "MIT"', 'license: "Apache-2.0"')
    cargo = _edit(root / member, "keywords.workspace = true", 'keywords = ["json", "zeta"]')
    assert _run(capsys, "write", "-q", "--root", str(root))[0] == 1
    assert (root / member).read_text(encoding="utf-8") == cargo.replace('["json", "zeta"]', '["json"]')


def test_reasons_from_an_edited_and_a_created_file_are_all_reported(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(tmp_path / "repo", 'files = ["codemeta.json", ".zenodo.json"]\nmanifests = []\n')
    (root / "codemeta.json").unlink()
    _edit(root / "CITATION.cff", 'license: "Apache-2.0"', 'license: "MIT AND Apache-2.0"')
    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert (
        out.splitlines()[0]
        == "wrote codemeta.json, leaving out license: a licence list can only say OR, not AND or WITH"
    )
    assert any(line.endswith("(edit it by hand: Zenodo takes one licence id)") for line in out.splitlines())


def test_a_created_codemeta_json_takes_contributors_and_non_ascii_names(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = _synthetic(
        tmp_path / "repo", 'source = ".zenodo.json"\nfiles = ["codemeta.json", ".zenodo.json"]\nmanifests = []\n'
    )
    (root / "codemeta.json").unlink()
    _edit(root / ".zenodo.json", '"Turing, Alan"', '"Skłodowska Curie, Marie"')
    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    text = (root / "codemeta.json").read_text(encoding="utf-8")
    assert '"familyName": "Skłodowska Curie"' in text
    assert json.loads(text)["contributor"] == [{"@type": "Person", "givenName": "Grace", "familyName": "Hopper"}]

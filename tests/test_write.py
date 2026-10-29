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
    assert (root / name).read_bytes() == (EXPECTED / name).read_bytes()
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
    assert 'title: "Planted"' in written or "title: Planted" in written


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


def test_r9lab_context_is_rewritten(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "r9lab"
    shutil.copytree(FIXTURES / "r9lab", root)
    before = (root / "codemeta.json").read_text(encoding="utf-8")
    assert _run(capsys, "write", "--root", str(root))[1].startswith("wrote codemeta.json\n")
    assert (root / "codemeta.json").read_text(encoding="utf-8") == before.replace("codemeta/4.0", "codemeta/3.0")


def test_d2_gap_is_left_alone(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'source = "pyproject.toml"\nwrite-manifests = "all"\n')
    codemeta = root / "codemeta.json"
    codemeta.write_text(codemeta.read_text(encoding="utf-8").replace("zenodo.1234567", "zenodo.7"), encoding="utf-8")
    before = _snapshot(root)

    code, out, _ = _run(capsys, "write", "--root", str(root))
    assert code == 1
    assert _snapshot(root) == before
    [line, _] = out.splitlines()
    assert "codemeta.json" in line
    assert "identifier" in line
    assert line.endswith(" (edit it by hand)")


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


def test_write_reports_as_check_does(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _synthetic(tmp_path / "repo", 'write-manifests = ["keywords"]\n')
    shutil.copy(PLANTED / "pyproject.toml", root / "pyproject.toml")
    shutil.copy(PLANTED / "codemeta.json", root / "codemeta.json")

    code, out, _ = _run(capsys, "write", "--root", str(tmp_path / "repo"))
    lines = out.splitlines()
    assert (code, lines[:2]) == (1, ["wrote codemeta.json", "wrote pyproject.toml"])
    [line] = [line for line in lines if "[version-mismatch]" in line]
    assert line.startswith("pyproject.toml: error[version-mismatch] version: ")
    assert line.endswith(" (edit it by hand, or add version to write-manifests)")
    assert re.fullmatch(r"\d+ errors?, 0 warnings in 6 files", lines[-1])

    shutil.copy(PLANTED / "codemeta.json", root / "codemeta.json")
    code, out, err = _run(capsys, "write", "--root", str(root), "--format", "json")
    report = json.loads(out)
    assert (code, err) == (1, "wrote codemeta.json\n")
    assert {f["rule"] for f in report["findings"]} >= {"version-mismatch"}

    shutil.copy(PLANTED / "codemeta.json", root / "codemeta.json")
    code, out, _ = _run(capsys, "write", "-q", "--root", str(root))
    assert code == 1
    assert all(": error[" in line for line in out.splitlines())

    monkeypatch.setenv("FORCE_COLOR", "1")
    assert "\033[1;31merror\033[0m[version-mismatch]" in _run(capsys, "write", "--root", str(root))[1]


def test_an_ignored_finding_is_not_written(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = _synthetic(tmp_path / "repo", 'ignore = ["version-mismatch", "context-mismatch"]\n')
    codemeta = root / "codemeta.json"
    text = codemeta.read_text(encoding="utf-8").replace('"1.2.3"', '"2.0.0"').replace("codemeta/3.0", "codemeta/3.1")
    codemeta.write_text(text, encoding="utf-8")

    assert _run(capsys, "write", "-q", "--root", str(root)) == (0, "", "")
    assert codemeta.read_text(encoding="utf-8") == text


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


# Text edits that each plant one disagreement in the synthetic set, with the term it plants.
# .zenodo.json holds no version or DOI: as the source it leaves a gap (D2), which write never fills.
GAPS = {".zenodo.json": {"version", "identifier"}}
EDITS = [
    ("codemeta.json", '"version": "1.2.3"', '"version": "2.0.0rc1"', "version"),
    ("codemeta.json", '"familyName": "Turing"', '"familyName": "Turning"', "author"),
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
        '"author": { "name": "Ada King", "email": "ada@example.org" }',
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

"""`citesync check` on the fixtures, against the findings in each cases.json, plus the D2 table and exit codes."""

import json
import shutil
from pathlib import Path

import jsonschema
import pytest

from citesync.cli import main

FIXTURES = Path(__file__).parent / "fixtures"
OUTPUT_SCHEMA = json.loads((Path(__file__).parent / "output.schema.json").read_text(encoding="utf-8"))
CASES = [
    (repo.name, case)
    for repo in sorted(FIXTURES.glob("*/"))
    for case in json.loads((repo / "cases.json").read_text(encoding="utf-8"))["cases"]
]


def _write_config(root: Path, config: dict[str, object]) -> None:
    if config:
        lines = [f"{key} = {json.dumps(value)}" for key, value in config.items()]
        (root / "citesync.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out, err = capsys.readouterr()
    return code, out, err


def _triples(items: list[dict[str, str]]) -> list[tuple[str, str, str]]:
    return [(i["code"], i["file"], i["term"]) for i in items]


@pytest.mark.parametrize(("repo", "case"), CASES, ids=[f"{r}-{c['name']}" for r, c in CASES])
def test_fixture_case(repo: str, case: dict, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / repo
    shutil.copytree(FIXTURES / repo, root)
    _write_config(root, case["config"])

    code, out, err = _run(capsys, "check", "--root", str(root), "--format", "json")
    report = json.loads(out)
    jsonschema.validate(report, OUTPUT_SCHEMA)
    assert (code, err) == (case["exit"], "")
    assert sorted(_triples(report["findings"])) == sorted(_triples(case["findings"]))
    assert sorted(_triples(report["info"])) == sorted(_triples(case["info"]))

    # Text: one line per finding, NOT_CHECKED only with -v, nothing when clean.
    _, text, _ = _run(capsys, "check", "--root", str(root))
    assert len(text.splitlines()) == len(case["findings"])
    _, verbose, _ = _run(capsys, "check", "--root", str(root), "-v")
    assert len(verbose.splitlines()) == len(case["findings"]) + len(case["info"])


PYPROJECT = '[build-system]\nrequires = []\n\n[project]\nname = "x"\n'
CFF = 'cff-version: 1.2.0\nmessage: "m"\ntitle: "x"\n'


def _codemeta(**fields: str) -> str:
    return json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "x", **fields})


# D2: the source has no slot (pyproject.toml has no DOI) or an empty value (CFF version "").
D2_TABLE = [
    pytest.param(
        "identifier",
        "pyproject.toml",
        {"CITATION.cff": CFF + 'doi: "10.1/a"\n', "codemeta.json": _codemeta(identifier="https://doi.org/10.1/b")},
        [("MISMATCH", "codemeta.json", "identifier")],
        [],
        id="no-slot-two-holders-disagree",
    ),
    pytest.param(
        "identifier",
        "pyproject.toml",
        {"CITATION.cff": CFF + 'doi: "10.1/a"\n', "codemeta.json": _codemeta(identifier="https://doi.org/10.1/A")},
        [],
        [],
        id="no-slot-two-holders-agree",
    ),
    pytest.param(
        "identifier", "pyproject.toml", {"CITATION.cff": CFF + 'doi: "10.1/a"\n'}, [], [], id="no-slot-one-holder"
    ),
    pytest.param(
        "identifier",
        "pyproject.toml",
        {"CITATION.cff": CFF},
        [],
        [("NOT_CHECKED", "", "identifier")],
        id="no-slot-no-holder",
    ),
    pytest.param(
        "version",
        "CITATION.cff",
        {
            "CITATION.cff": CFF + 'version: ""\n',
            "codemeta.json": _codemeta(version="1.0.0"),
            ".zenodo.json": json.dumps({"title": "x", "version": "2.0.0"}),
        },
        [("MISMATCH", ".zenodo.json", "version")],
        [],
        id="empty-source-two-holders-disagree",
    ),
    pytest.param(
        "version",
        "CITATION.cff",
        {"CITATION.cff": CFF + 'version: ""\n', "codemeta.json": _codemeta(version="1.0.0")},
        [],
        [],
        id="empty-source-one-holder",
    ),
]


@pytest.mark.parametrize(("term", "source", "files", "findings", "info"), D2_TABLE)
def test_d2_gap(
    term: str,
    source: str,
    files: dict[str, str],
    findings: list[tuple[str, str, str]],
    info: list[tuple[str, str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--source", source, "--json")
    report = json.loads(out)
    assert _triples(report["findings"]) == findings
    assert [t for t in _triples(report["info"]) if t[2] == term] == info
    assert code == (1 if findings else 0)


def test_semver_prerelease_equals_pep440(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF + "version: 0.3.1-rc.1\n", encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(version="0.3.1rc1"), encoding="utf-8")
    assert _run(capsys, "check", "--root", str(tmp_path)) == (0, "", "")
    (tmp_path / "codemeta.json").write_text(_codemeta(version="0.3.1rc2"), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path))
    assert (code, out.split(":")[0]) == (1, "MISMATCH codemeta.json")


def test_findings_are_sorted_and_text_matches_codemeta_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF + "version: 1.0.0\nlicense: MIT\n", encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/4.0", "name": "y", "version": "2.0.0", "license": "MIT"}),
        encoding="utf-8",
    )
    (tmp_path / ".zenodo.json").write_text(json.dumps({"title": "z", "license": "apache-2.0"}), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path))
    assert code == 1
    assert [line.split(":")[0:2] for line in out.splitlines()] == [
        ["MISMATCH .zenodo.json", " license"],
        ["MISMATCH .zenodo.json", " name"],
        ["CONTEXT codemeta.json", " @context"],
        ["MISMATCH codemeta.json", " name"],
        ["MISMATCH codemeta.json", " version"],
    ]


def test_github_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github", "-v")
    lines = out.splitlines()
    assert code == 1
    assert lines[0] == "::error file=codemeta.json,title=citesync MISMATCH::name: 'y', CITATION.cff has 'x'"
    assert all(line.startswith("::notice title=citesync NOT_CHECKED::") for line in lines[1:])


@pytest.mark.parametrize(
    ("files", "args", "message"),
    [
        ({"codemeta.json": _codemeta()}, [], "CITATION.cff: the source file is missing"),
        ({"CITATION.cff": CFF.replace("1.2.0", "1.1.0")}, [], "cff-version '1.1.0'"),
        ({"CITATION.cff": CFF, "codemeta.json": '{"@context": "https://schema.org"}'}, [], "is not CodeMeta"),
        ({"CITATION.cff": CFF, "codemeta.json": "{"}, [], "codemeta.json: cannot parse"),
        ({"CITATION.cff": CFF, "citesync.toml": 'manifests = ["sub/package.json"]'}, [], "sub/package.json: listed"),
        ({"CITATION.cff": CFF}, ["--source", "README.md"], "--source: source must name one of"),
    ],
)
def test_exit_2(
    files: dict[str, str], args: list[str], message: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    code, out, err = _run(capsys, "check", "--root", str(tmp_path), *args)
    assert (code, out) == (2, "")
    assert message in err


def test_write_is_not_in_this_build(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    code, _, err = _run(capsys, "write", "--root", str(tmp_path))
    assert (code, err) == (2, "citesync: write is not implemented in this build\n")

"""`citesync check` on the fixtures, against the findings in each cases.json, plus the D2 table and exit codes."""

import io
import json
import os
import re
import shutil
import subprocess
import sys
import time
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path

import jsonschema
import pytest

from citesync import codecs
from citesync.check import Finding, compare
from citesync.cli import _sarif, main
from citesync.formats import Doc
from citesync.mapping import TERMS

FIXTURES = Path(__file__).parent / "fixtures"
FIX = "Make the file agree with the source, or the other way round if the source is wrong."
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


def _triples(items: list[dict]) -> list[tuple[str, str | None, str | None]]:
    return [(i["rule"], i["file"], i["term"]) for i in items]


def _at(items: list[dict]) -> list[tuple[int | None, int | None]]:
    """Where each finding points; an expected entry without ``line`` points nowhere."""
    return [(i.get("line"), i.get("column")) for i in items]


def _split(report: dict) -> tuple[list[dict], list[dict]]:
    """The findings that fail a run, and the info."""
    findings = report["findings"]
    return [f for f in findings if f["severity"] != "info"], [f for f in findings if f["severity"] == "info"]


def _refresh(data: dict, name: str, code: int, findings: list[dict], info: list[dict]) -> None:
    """Set a case's exit code and findings from actual output, keeping the hand-written entry that matches."""
    case = next(c for c in data["cases"] if c["name"] == name)
    case["exit"] = code
    for key, actual in (("findings", findings), ("info", info)):
        old = dict(zip(_triples(case[key]), case[key], strict=True))
        case[key] = [
            _place(old.get(t) or {"rule": f["rule"], "file": f["file"], "term": f["term"], "why": f["message"]}, f)
            for t, f in zip(_triples(actual), actual, strict=True)
        ]


def _place(entry: dict, actual: dict) -> dict:
    """``entry`` with the line and column of ``actual``, or without them when it has none."""
    entry = {k: v for k, v in entry.items() if k not in {"line", "column"}}
    return entry | ({"line": actual["line"], "column": actual["column"]} if actual["line"] else {})


@pytest.mark.parametrize(("repo", "case"), CASES, ids=[f"{r}-{c['name']}" for r, c in CASES])
def test_fixture_case(
    repo: str, case: dict, tmp_path: Path, capsys: pytest.CaptureFixture[str], update_expected: Callable[..., bool]
) -> None:
    root = tmp_path / repo
    shutil.copytree(FIXTURES / repo, root)
    _write_config(root, case["config"])

    code, out, err = _run(capsys, "check", "--root", str(root), "--format", "json")
    report = json.loads(out)
    jsonschema.validate(report, OUTPUT_SCHEMA)
    assert err == ""
    findings, info = _split(report)
    if update_expected(FIXTURES / repo / "cases.json", lambda data: _refresh(data, case["name"], code, findings, info)):
        return
    assert code == case["exit"]
    assert _triples(findings) == _triples(case["findings"])
    assert _triples(info) == _triples(case["info"])
    assert _at(findings) == _at(case["findings"])
    assert _at(info) == _at(case["info"])

    # Text: two lines per finding (the help under it) and a summary, info only with -v, and the
    # count write could fix when check fails.
    fixable = case["exit"] == 1
    _, text, _ = _run(capsys, "check", "--root", str(root))
    assert len(text.splitlines()) == 2 * len(case["findings"]) + 1 + fixable
    _, verbose, _ = _run(capsys, "check", "--root", str(root), "-v")
    assert len(verbose.splitlines()) == 2 * (len(case["findings"]) + len(case["info"])) + 1 + fixable


PYPROJECT = '[build-system]\nrequires = []\n\n[project]\nname = "x"\n'
CFF = 'cff-version: 1.2.0\nmessage: "m"\ntitle: "x"\n'


def _codemeta(**fields: object) -> str:
    return json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "x", **fields})


# D2: the source has no slot (pyproject.toml has no DOI) or an empty value (CFF version "").
D2_TABLE = [
    pytest.param(
        "identifier",
        "pyproject.toml",
        {"CITATION.cff": CFF + 'doi: "10.1/a"\n', "codemeta.json": _codemeta(identifier="https://doi.org/10.1/b")},
        [("doi-mismatch", "codemeta.json", "identifier")],
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
        [("not-checked", None, "identifier")],
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
        [("version-mismatch", ".zenodo.json", "version")],
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
    errors, notes = _split(json.loads(out))
    assert _triples(errors) == findings
    assert [t for t in _triples(notes) if t[2] == term] == info
    assert code == (1 if findings else 0)


@pytest.mark.parametrize("keywords", ["alpha, beta,gamma", "alpha\uff0c beta\u3001gamma"])
def test_codemeta_keywords_may_be_one_comma_separated_string(
    keywords: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """schema.org lets ``keywords`` be one Text with commas between the keywords, full-width ones too."""
    (tmp_path / "CITATION.cff").write_text(CFF + "keywords: [alpha, beta, gamma]\n", encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(keywords=keywords), encoding="utf-8")
    assert _run(capsys, "check", "--root", str(tmp_path)) == (0, "0 errors, 0 warnings in 2 files\n", "")


def test_findings_are_sorted_and_text_matches_codemeta_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF + "version: 1.0.0\nlicense: MIT\n", encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(
        json.dumps({"@context": "https://w3id.org/codemeta/4.0", "name": "y", "version": "2.0.0", "license": "MIT"}),
        encoding="utf-8",
    )
    (tmp_path / ".zenodo.json").write_text(json.dumps({"title": "z", "license": "apache-2.0"}), encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('codemeta-version = "3.0"\n', encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path))
    assert code == 1
    assert _run(capsys, "check", "--root", str(tmp_path), "--quiet")[1] == out.rsplit("5 errors", 1)[0]
    assert [line for line in out.splitlines() if not line.startswith("  help: ")] == [
        ".zenodo.json:1:16: error[license-mismatch] license: 'apache-2.0', CITATION.cff has 'MIT'",
        ".zenodo.json:1:2: error[name-mismatch] name: 'z', CITATION.cff has 'x'",
        "codemeta.json:1:2: error[context-mismatch] @context: 4.0, configured 3.0",
        "codemeta.json:1:47: error[name-mismatch] name: 'y', CITATION.cff has 'x'",
        "codemeta.json:1:60: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'",
        "5 errors, 0 warnings in 3 files",
        "5 fixable with `citesync write`",
    ]


def test_github_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github", "-v")
    lines = out.splitlines()
    assert code == 1
    assert lines[0] == (
        "::error file=codemeta.json,line=1,col=47,title=citesync name-mismatch::"
        f"name: 'y', CITATION.cff has 'x'%0Ahelp: {FIX}"
    )
    assert all(line.startswith("::notice title=citesync not-checked::") for line in lines[1:-1])
    assert lines[-1] == "::notice::citesync: 1 error, 0 warnings in 2 files"


def test_sarif_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "sarif")
    log = json.loads(out)
    (run,) = log["runs"]
    driver = run["tool"]["driver"]
    assert (code, log["version"], driver["name"]) == (1, "2.1.0", "citesync")
    assert driver["informationUri"] == "https://github.com/simonvanlierde/citesync"
    assert [(r["id"], r["defaultConfiguration"]["level"]) for r in driver["rules"]] == [("name-mismatch", "error")]
    assert driver["rules"][0]["helpUri"].endswith("/docs/rules.md#name-mismatch")
    (result,) = run["results"]
    assert (result["ruleId"], result["level"]) == ("name-mismatch", "error")
    assert result["message"]["text"] == "name: 'y', CITATION.cff has 'x'"
    assert [loc["physicalLocation"]["artifactLocation"]["uri"] for loc in result["locations"]] == ["codemeta.json"]
    assert result["locations"][0]["physicalLocation"]["region"] == {"startLine": 1, "startColumn": 47}


def test_sarif_levels_and_region() -> None:

    log = _sarif(
        [
            Finding("a.json", "name", "name-mismatch", "m", line=3, column=5),
            Finding("a.json", "author", "role-dangling", "m"),
            Finding("a.json", "x", "not-checked", "m"),
        ],
        "",
    )
    run = log["runs"][0]
    assert [r["level"] for r in run["results"]] == ["error", "warning", "note"]
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["name-mismatch", "not-checked", "role-dangling"]
    assert run["results"][0]["locations"][0]["physicalLocation"]["region"] == {"startLine": 3, "startColumn": 5}
    assert "region" not in run["results"][1]["locations"][0]["physicalLocation"]


def test_every_sarif_result_has_a_location(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A finding on no file, a not-checked term no file holds, has nowhere to point, so SARIF leaves it out."""
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    _, out, _ = _run(capsys, "check", "-v", "--root", str(tmp_path), "--format", "sarif")
    run = json.loads(out)["runs"][0]
    assert [r["ruleId"] for r in run["results"]] == ["name-mismatch"]
    assert [r["id"] for r in run["tool"]["driver"]["rules"]] == ["name-mismatch"]


@pytest.mark.parametrize(
    ("files", "args", "message"),
    [
        ({"codemeta.json": _codemeta()}, [], "CITATION.cff: the source file is missing"),
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


@pytest.mark.parametrize(
    ("name", "content", "message", "position"),
    [
        ("CITATION.cff", b"cff-version: 1.2.0\ntitle: \xff\n", "not UTF-8 at byte 26", None),
        ("CITATION.cff", b"cff-version: 1.2.0\ntitle: [x\n", "expected ',' or ']', but got '<stream end>'", (3, 1)),
        ("CITATION.cff", CFF.replace("1.2.0", "1.1.0").encode(), "cff-version '1.1.0', citesync reads 1.2.0", None),
        ("codemeta.json", b"{", "Expecting property name enclosed in double quotes", (1, 2)),
        ("codemeta.json", b'{"@context": "https://schema.org"}', "is not CodeMeta", None),
        ("codemeta.json", b"[]", "the top level is not a mapping", None),
        ("pyproject.toml", b"[project\n", "Expected ']' at the end of a table declaration", (1, 9)),
        ("Cargo.toml", b'package = "x"\n', "unexpected shape", None),
        ("Cargo.toml", b"workspace = 3\n", "unexpected shape", None),
        ("Cargo.toml", b"workspace = true\n", "unexpected shape", None),
        ("pyproject.toml", b'[build-system]\n[project]\nname = "x"\ndynamic = 1\n', "unexpected shape", None),
    ],
)
def test_unreadable_file_is_a_finding(
    name: str,
    content: bytes,
    message: str,
    position: tuple[int, int] | None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / name).write_bytes(content)
    code, out, err = _run(capsys, "check", "--root", str(tmp_path), "--json")
    report = json.loads(out)
    jsonschema.validate(report, OUTPUT_SCHEMA)
    [found] = [f for f in report["findings"] if f["rule"] == "unreadable"]
    assert (code, err, found["file"], found["term"]) == (1, "", name, None)
    assert report["summary"]["files"] == (1 if name == "CITATION.cff" else 2)
    assert message in found["message"]
    assert (found["line"], found["column"]) == (position or (None, None))
    _, github, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github")
    where = f"line={position[0]},col={position[1]}," if position else ""
    assert f"::error file={name},{where}title=citesync unreadable::" in github


@pytest.mark.parametrize(("name", "text"), [(".zenodo.json", '{"title": "x"}'), ("pyproject.toml", PYPROJECT)])
def test_a_byte_order_mark_is_named(name: str, text: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _check_json(tmp_path, capsys, {"CITATION.cff": "\ufeff" + CFF, name: "\ufeff" + text})
    assert [(f["file"], f["message"]) for f in report["findings"] if f["rule"] == "unreadable"] == [
        (name, "starts with a byte order mark: save it as UTF-8 without one")
    ]


def test_a_file_through_a_symlinked_directory_out_of_the_repo_is_unreadable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "codemeta.json").write_text(_codemeta(name="secret"), encoding="utf-8")
    root = tmp_path / "repo"
    root.mkdir()
    (root / "docs").symlink_to(tmp_path / "outside")
    files = {"CITATION.cff": CFF, "citesync.toml": 'files = ["docs/codemeta.json"]\n'}
    report = _check_json(root, capsys, files)
    assert [(f["rule"], f["file"], f["message"]) for f in _split(report)[0]] == [
        ("unreadable", "docs/codemeta.json", "resolves outside the repo root")
    ]
    assert "secret" not in json.dumps(report)


def test_unreadable_source_leaves_the_rest_checked(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _check_json(
        tmp_path,
        capsys,
        {
            "CITATION.cff": "title: [\n",
            "codemeta.json": _codemeta(version="1.0.0"),
            ".zenodo.json": json.dumps({"title": "x", "version": "2.0.0"}),
        },
    )
    findings, info = _split(report)
    assert _triples(findings) == [
        ("version-mismatch", ".zenodo.json", "version"),
        ("unreadable", "CITATION.cff", None),
    ]
    # CITATION.cff has no contributor list, and no other file holds one
    cff_terms = sorted(t for t in TERMS if t != "contributor")
    assert [(f["file"], f["term"]) for f in info] == [*(("CITATION.cff", t) for t in cff_terms), (None, "contributor")]
    assert {f["message"] for f in info[:-1]} == {"not compared with the source: it can't be read"}
    assert report["summary"] == {"files": 3, "errors": 2, "warnings": 0, "info": 10}


def test_unexpected_error_is_exit_2(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_: object) -> None:
        msg = "boom"
        raise RuntimeError(msg)

    monkeypatch.setattr("citesync.cli.check", boom)
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    code, out, err = _run(capsys, "check", "--root", str(tmp_path))
    assert (code, out) == (2, "")
    assert err == f"citesync: {tmp_path}: unexpected error: RuntimeError: boom\n"


def _people(*names: str, orcid: str | None = None) -> list[dict[str, str]]:
    people = [dict(zip(("givenName", "familyName"), n.split(), strict=True)) for n in names]
    if orcid:
        people[0]["@id"] = f"https://orcid.org/{orcid}"
    return people


def _pyproject(*lines: str) -> str:
    return PYPROJECT + "\n".join(lines) + "\n"


def _check_json(tmp_path: Path, capsys: pytest.CaptureFixture[str], files: dict[str, str], *args: str) -> dict:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    _, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--json", *args)
    return json.loads(out)


ORCID_A, ORCID_B = "0000-0002-1825-0097", "0000-0001-5109-3700"
CFF_AB = CFF + "authors:\n  - {given-names: A, family-names: B}\n"


@pytest.mark.parametrize(
    ("source", "files", "expected"),
    [
        pytest.param(
            "CITATION.cff",
            {
                "CITATION.cff": CFF_AB,
                "codemeta.json": _codemeta(author=_people("A B", "X Y")),
                "pyproject.toml": _pyproject('authors = [{ name = "A B" }]'),
            },
            [("author-mismatch", "codemeta.json", "author")],
            id="orcid-source-names-only-against-source",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": _pyproject('authors = [{ name = "A B" }]'),
                "CITATION.cff": CFF + "authors:\n  - {given-names: A, family-names: C}\n",
                "codemeta.json": _codemeta(author=_people("A B")),
            },
            [("author-mismatch", "CITATION.cff", "author")],
            id="manifest-source-blames-only-the-disagreeing-file",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": _pyproject('authors = [{ name = "A B" }]'),
                "CITATION.cff": CFF_AB.replace("B}", f"B, orcid: 'https://orcid.org/{ORCID_A}'}}"),
                "codemeta.json": _codemeta(author=_people("A B", orcid=ORCID_B)),
            },
            [("author-mismatch", "codemeta.json", "author")],
            id="manifest-source-orcids-compared-between-holders",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": _pyproject('keywords = ["a"]'),
                "CITATION.cff": CFF + "keywords: [a, b]\n",
                "codemeta.json": _codemeta(keywords=["a", "c"]),
            },
            [("keywords-mismatch", "codemeta.json", "keywords")],
            id="manifest-source-citation-keywords-equal",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": _pyproject('keywords = ["a"]'),
                "CITATION.cff": CFF + "keywords: [a]\n",
                "Cargo.toml": '[package]\nname = "x"\nkeywords = ["z"]\n',
            },
            [("keywords-not-subset", "Cargo.toml", "keywords")],
            id="manifest-source-other-manifest-subset-of-citation",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": _pyproject('keywords = ["a"]'),
                "CITATION.cff": CFF + "keywords: [a, b]\n",
                "Cargo.toml": '[package]\nname = "x"\nkeywords = ["b"]\n',
            },
            [],
            id="manifest-source-no-rule-between-manifests",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": _pyproject('description = "z"'),
                "CITATION.cff": CFF + "abstract: a\n",
                "codemeta.json": _codemeta(name="y", description="b"),
            },
            [("description-mismatch", "codemeta.json", "description"), ("name-mismatch", "codemeta.json", "name")],
            id="manifest-source-citation-names-compared-between-holders",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": PYPROJECT,
                "CITATION.cff": CFF_AB,
                "codemeta.json": _codemeta(author=_people("A C")),
            },
            [("author-mismatch", "codemeta.json", "author")],
            id="manifest-source-without-authors-holders-compared-by-name",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "pyproject.toml": _pyproject('authors = [{ name = "A B" }]'),
                "CITATION.cff": CFF_AB,
                "codemeta.json": _codemeta(author=_people("A B", "X Y")),
            },
            [("author-mismatch", "codemeta.json", "author")],
            id="manifest-source-holders-with-different-author-counts",
        ),
        pytest.param(
            "pyproject.toml",
            {"pyproject.toml": _pyproject('keywords = ["a", "z"]'), "CITATION.cff": CFF + "keywords: [a]\n"},
            [("keywords-not-subset", "CITATION.cff", "keywords")],
            id="manifest-source-keywords-not-in-citation",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "citesync.toml": "keywords-case-sensitive = true\n",
                "pyproject.toml": _pyproject('keywords = ["lca"]'),
                "CITATION.cff": CFF + "keywords: [lca]\n",
                "codemeta.json": _codemeta(keywords=["LCA"]),
            },
            [
                ("keywords-mismatch", "codemeta.json", "keywords"),
                ("keywords-not-subset", "codemeta.json", "keywords"),
            ],
            id="manifest-source-holders-keywords-case-sensitive",
        ),
        pytest.param(
            "pyproject.toml",
            {
                "citesync.toml": "keywords-case-sensitive = true\n",
                "pyproject.toml": PYPROJECT,
                "CITATION.cff": CFF + "keywords: [lca]\n",
                "codemeta.json": _codemeta(keywords=["LCA"]),
            },
            [("keywords-mismatch", "codemeta.json", "keywords")],
            id="manifest-source-without-keywords-case-sensitive",
        ),
        pytest.param(
            "pyproject.toml",
            {"pyproject.toml": '[project]\nname = "x"\nversion = "1.0.0"\n', "CITATION.cff": CFF + "version: 2.0.0\n"},
            [("version-mismatch", "CITATION.cff", "version")],
            id="unreleased-manifest-source-still-checked",
        ),
        pytest.param(
            "CITATION.cff",
            {
                "citesync.toml": 'files = ["codemeta.json"]\n',
                "CITATION.cff": CFF,
                "codemeta.json": _codemeta(),
                ".zenodo.json": json.dumps({"title": "z"}),
            },
            [],
            id="files-config-limits-the-citation-files",
        ),
    ],
)
def test_holders_beyond_the_source(
    source: str,
    files: dict[str, str],
    expected: list[tuple[str, str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    report = _check_json(tmp_path, capsys, files, "--source", source)
    assert _triples(_split(report)[0]) == expected


def test_blame_does_not_depend_on_config_order(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "pyproject.toml": PYPROJECT,
        "CITATION.cff": CFF + 'doi: "10.1/a"\n',
        "codemeta.json": _codemeta(identifier="10.1/b"),
        ".zenodo.json": json.dumps({"title": "x", "doi": "10.1/c"}),
    }
    reports = [
        _check_json(
            tmp_path, capsys, {**files, "citesync.toml": f"files = {json.dumps(order)}\n"}, "--source", "pyproject.toml"
        )
        for order in (list(files)[1:], list(files)[:0:-1])
    ]
    for report in reports:
        report["findings"] = [f for f in report["findings"] if f["term"] == "identifier"]
    assert reports[0] == reports[1]
    assert [(f["file"], f["message"]) for f in reports[0]["findings"]] == [
        (".zenodo.json", "'10.1/c', CITATION.cff has '10.1/a'"),
        ("codemeta.json", "'10.1/b', CITATION.cff has '10.1/a'"),
    ]


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        ("", []),
        (
            "keywords-case-sensitive = true\n",
            [
                (
                    "keywords-mismatch",
                    "codemeta.json",
                    "keywords",
                    "missing life cycle, LCA; extra Life Cycle, lca (compared with CITATION.cff)",
                ),
                (
                    "keywords-not-subset",
                    "pyproject.toml",
                    "keywords",
                    "Lca, Life Cycle: in pyproject.toml, not in CITATION.cff",
                ),
            ],
        ),
    ],
    ids=["default-casefolded", "case-sensitive"],
)
def test_keywords_compare_like_names(
    config: str, expected: list[tuple[str, ...]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        "citesync.toml": config,
        "CITATION.cff": CFF + "keywords: [life  cycle, LCA]\n",
        "codemeta.json": _codemeta(keywords=["Life Cycle", "lca"]),
        "pyproject.toml": _pyproject('keywords = ["Lca", "Life Cycle"]'),
    }
    report = _check_json(tmp_path, capsys, files)
    assert [(f["rule"], f["file"], f["term"], f["message"]) for f in _split(report)[0]] == expected


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        (
            "",
            [
                (
                    "keywords-mismatch",
                    "codemeta.json",
                    "keywords",
                    (
                        "'industrial-ecology' differs from 'industrial ecology' only in separators;"
                        " 'life_cycle' differs from 'life cycle' only in separators (compared with CITATION.cff)"
                    ),
                ),
                (
                    "keywords-not-subset",
                    "pyproject.toml",
                    "keywords",
                    (
                        "Industrial_Ecology (CITATION.cff has 'industrial ecology': differs only in separators), x:"
                        " in pyproject.toml, not in CITATION.cff"
                    ),
                ),
            ],
        ),
        (
            "keywords-ignore-separators = true\n",
            [("keywords-not-subset", "pyproject.toml", "keywords", "x: in pyproject.toml, not in CITATION.cff")],
        ),
    ],
    ids=["near-miss-named", "separators-ignored"],
)
def test_keywords_that_differ_only_in_separators(
    config: str, expected: list[tuple[str, ...]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        "citesync.toml": config,
        "CITATION.cff": CFF + "keywords: [industrial ecology, life cycle, lca]\n",
        "codemeta.json": _codemeta(keywords=["industrial-ecology", "life_cycle", "lca"]),
        "pyproject.toml": _pyproject('keywords = ["Industrial_Ecology", "x"]'),
    }
    report = _check_json(tmp_path, capsys, files)
    assert [(f["rule"], f["file"], f["term"], f["message"]) for f in _split(report)[0]] == expected


def test_many_keywords_compare_in_linear_time() -> None:
    words = [f"w{i}" for i in range(20_000)]
    ref = Doc("CITATION.cff", "cff-1.2.0", {"keywords": (*words, "big data")}, frozenset(), "1.2.0", release=True)
    doc = Doc("codemeta.json", "codemeta", {"keywords": (*words, "big-data", "x")}, frozenset(), "3.0", release=True)
    start = time.perf_counter()
    finding = compare("keywords", ref, doc, kw_key=codecs.name_key)
    assert time.perf_counter() - start < 1
    assert finding is not None
    assert (
        finding.message == "extra x; 'big-data' differs from 'big data' only in separators (compared with CITATION.cff)"
    )


def test_order_and_case_do_not_matter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "CITATION.cff": CFF + "keywords: [b, a]\nauthors:\n  - {given-names: Ada, family-names: Lovelace}\n",
        "codemeta.json": _codemeta(keywords=["a", "b"], author=_people("ada lovelace")),
    }
    assert _split(_check_json(tmp_path, capsys, files))[0] == []


MISMATCHED = [("author-mismatch", "codemeta.json", "author")]


@pytest.mark.parametrize(
    ("given", "family", "other", "expected"),
    [
        pytest.param("呦呦", "屠", {"name": "屠呦呦"}, [], id="one-name-family-first-no-space"),
        pytest.param("Youyou", "Tu", {"name": "Tu Youyou"}, [], id="one-name-family-first"),
        pytest.param("Youyou", "Tu", {"name": "Youyou Tu"}, [], id="one-name-given-first"),
        pytest.param("Simon", "Lierde", {"givenName": "Lierde", "familyName": "Simon"}, MISMATCHED, id="split-swapped"),
        pytest.param("Youyou", "Tu", {"name": "Tu You"}, MISMATCHED, id="one-name-differs"),
    ],
)
def test_family_first_names_match_only_against_one_name(
    given: str, family: str, other: dict, expected: list, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        "CITATION.cff": CFF + f"authors:\n  - {{given-names: {given}, family-names: {family}}}\n",
        "codemeta.json": _codemeta(author=[other]),
    }
    assert _triples(_split(_check_json(tmp_path, capsys, files))[0]) == expected


@pytest.mark.parametrize(
    ("orcid", "expected"), [(ORCID_A, []), (ORCID_B, [f"'? ({ORCID_B})', CITATION.cff has '? ({ORCID_A})'"])]
)
def test_authors_without_names_compare_by_orcid(
    orcid: str, expected: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {
        "CITATION.cff": CFF + f"authors:\n  - orcid: https://orcid.org/{ORCID_A}\n",
        "codemeta.json": _codemeta(author=[{"@id": f"https://orcid.org/{orcid}"}]),
    }
    assert [f["message"] for f in _split(_check_json(tmp_path, capsys, files))[0]] == expected


@pytest.mark.parametrize(("length", "shown"), [(80, "n" * 80), (81, "n" * 77 + "...")])
def test_long_values_are_cut_in_messages(
    length: int, shown: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    files = {"CITATION.cff": CFF, "codemeta.json": _codemeta(name="n" * length)}
    [finding] = _split(_check_json(tmp_path, capsys, files))[0]
    assert finding["message"] == f"'{shown}', CITATION.cff has 'x'"


@pytest.mark.parametrize(
    ("doi", "expected"), [("10.1/a", []), ("10.1/b", [("doi-mismatch", "codemeta.json", "identifier")])]
)
def test_codemeta_property_value_doi(
    doi: str, expected: list[tuple[str, str, str]], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    identifier = [
        {"@type": "PropertyValue", "propertyID": "SWHID", "value": "swh:1:dir:" + "0" * 40},
        {"@type": "PropertyValue", "propertyID": "DOI", "value": doi},
    ]
    files = {"CITATION.cff": CFF + 'doi: "10.1/a"\n', "codemeta.json": _codemeta(identifier=identifier)}
    assert _triples(_split(_check_json(tmp_path, capsys, files))[0]) == expected


SYNTHETIC = FIXTURES / "synthetic-agree"
# One planted disagreement per row, in synthetic-agree with CITATION.cff as the source.
PLANTED = [
    (
        "codemeta.json",
        '"name": "synthagree"',
        '"name": "other"',
        "name-mismatch",
        "name",
        "'other', CITATION.cff has 'synthagree'",
    ),
    (
        "Cargo.toml",
        'version = "1.2.3"',
        'version = "1.2.4"',
        "version-mismatch",
        "version",
        "'1.2.4', CITATION.cff has '1.2.3'",
    ),
    (
        ".zenodo.json",
        '"Lovelace, Ada",\n      "orcid": "0000-0002-1825-0097"\n    },\n    {\n      "name": "Turing, Alan"',
        '"Turing, Alan"\n    },\n    {\n      "name": "Lovelace, Ada",\n      "orcid": "0000-0002-1825-0097"',
        "author-mismatch",
        "author",
        (
            "'Alan Turing; Ada Lovelace (0000-0002-1825-0097)',"
            " CITATION.cff has 'Ada Lovelace (0000-0002-1825-0097); Alan Turing'"
        ),
    ),
    ("codemeta.json", "0000-0002-1825-0097", "0000-0001-5109-3700", "author-mismatch", "author", None),
    ("pyproject.toml", 'license = "Apache-2.0"', 'license = "MIT"', "license-mismatch", "license", None),
    ("codemeta.json", "zenodo.1234567", "zenodo.7654321", "doi-mismatch", "identifier", None),
    (
        ".zenodo.json",
        '"https://github.com/example/synthagree"',
        '"https://github.com/example/other"',
        "repository-mismatch",
        "codeRepository",
        None,
    ),
    (
        "package.json",
        "git+https://github.com/example/synthagree.git",
        "github:example/other",
        "repository-mismatch",
        "codeRepository",
        None,
    ),
    (
        ".zenodo.json",
        '"description": "A made-up',
        '"description": "Another made-up',
        "description-mismatch",
        "description",
        None,
    ),
    ("codemeta.json", '"gamma", "delta"]', '"gamma"]', "keywords-mismatch", "keywords", None),
    (
        "package.json",
        '"gamma", "delta"]',
        '"gamma", "delta", "omega"]',
        "keywords-not-subset",
        "keywords",
        "omega: in package.json, not in CITATION.cff",
    ),
    ("codemeta.json", "codemeta/3.0", "codemeta/2.0", "context-mismatch", "@context", "2.0, configured 3.0"),
]


@pytest.mark.parametrize(
    ("name", "old", "new", "code", "term", "detail"), PLANTED, ids=[f"{p[0]}-{p[4]}-{p[3]}" for p in PLANTED]
)
def test_one_planted_disagreement(
    name: str,
    old: str,
    new: str,
    code: str,
    term: str,
    detail: str | None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = tmp_path / "repo"
    shutil.copytree(SYNTHETIC, root)
    (root / "citesync.toml").write_text('codemeta-version = "3.0"\n', encoding="utf-8")
    text = (root / name).read_text(encoding="utf-8")
    assert text.count(old) == 1
    (root / name).write_text(text.replace(old, new), encoding="utf-8")
    code_, out, _ = _run(capsys, "check", "--root", str(root), "--json")
    findings, _ = _split(json.loads(out))
    assert (code_, _triples(findings)) == (1, [(code, name, term)])
    if detail is not None:
        assert findings[0]["message"] == detail


def test_not_checked_detail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    info = _check_json(tmp_path, capsys, {"CITATION.cff": CFF})["findings"]
    assert info[0] == {
        "rule": "not-checked",
        "severity": "info",
        "file": None,
        "term": "author",
        "message": "no file holds a value",
        "help": "Add the field to the source if the files should carry it.",
        "url": "https://github.com/simonvanlierde/citesync/blob/main/docs/rules.md#not-checked",
        "line": None,
        "column": None,
    }


def test_json_keeps_info_under_quiet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _check_json(tmp_path, capsys, {"CITATION.cff": CFF}, "-q")
    assert report["summary"]["info"] == len(_split(report)[1]) == 9


def test_schema_lets_a_minor_release_add_rules_and_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _check_json(tmp_path, capsys, {"CITATION.cff": CFF})
    report["findings"][0] |= {"rule": "orcid-checksum", "end_line": 3}
    report["summary"]["notes"] = 0
    jsonschema.validate(report, OUTPUT_SCHEMA)
    report["findings"][0]["rule"] = "Not_Kebab"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, OUTPUT_SCHEMA)


EPILOG = """\
exit codes:
  0  no error finding (warnings and info don't fail)
  1  an error finding; with write --diff, a change to make or a file it can't read
  2  citesync couldn't run: a bad config or option, a missing source file

config: the first of citesync.toml, .citesync.toml, [tool.citesync] in pyproject.toml,
[workspace.metadata.citesync] or [package.metadata.citesync] in Cargo.toml, or "citesync" in package.json

docs: https://github.com/simonvanlierde/citesync/blob/main/docs
"""


@pytest.mark.parametrize(
    ("args", "head"),
    [
        (
            ["--help"],
            """\
usage: citesync [-h] [-V] command ...

Check that CITATION.cff, codemeta.json, .zenodo.json and the package manifests
(pyproject.toml, Cargo.toml, package.json) agree, and rewrite them to match one source file.

positional arguments:
  command
    check        report where the files disagree with the source
    write        rewrite the files to agree with the source
    config       print the config in use and where it came from
    rules        list the rules
    explain      print a rule's documentation

options:
  -h, --help     show this help message and exit
  -V, --version  show the version and exit

""",
        ),
        (
            ["check", "--help"],
            """\
usage: citesync check [-h] [--root ROOT] [--source SOURCE] [--format {text,json,github,sarif}]
                      [--json] [--color {auto,always,never}] [-v | -q]

Report where the files disagree with the source.

options:
  -h, --help            show this help message and exit
  --root ROOT           repo root (default: the nearest directory up with a citation file or
                        config, else the git repo's top)
  --source SOURCE       the file the others must agree with; overrides config
  --format {text,json,github,sarif}
                        output format (default: text)
  --json                alias of --format json
  --color {auto,always,never}
                        colour the text output (default: auto, on a terminal unless NO_COLOR or
                        FORCE_COLOR say otherwise)
  -v, --verbose         also print info: fields not compared, manifests left out
  -q, --quiet           print only errors, and no summary

""",
        ),
    ],
    ids=["citesync", "check"],
)
def test_help(args: list[str], head: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("COLUMNS", "100")
    with pytest.raises(SystemExit) as exc:
        main(args)
    assert (exc.value.code, capsys.readouterr().out) == (0, head + EPILOG)


def test_no_command_prints_the_help_and_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main([])
    out, err = capsys.readouterr()
    assert (exc.value.code, out) == (2, "")
    assert err.startswith("usage: citesync [-h] [-V] command ...")


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["--version"])
    assert (exit_.value.code, capsys.readouterr().out) == (0, f"citesync {version('citesync')}\n")


def test_github_format_quiet_has_no_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    _, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github", "-q")
    assert out.splitlines() == [
        (
            "::error file=codemeta.json,line=1,col=47,title=citesync name-mismatch::"
            f"name: 'y', CITATION.cff has 'x'%0Ahelp: {FIX}"
        )
    ]


def test_github_format_escapes_the_file_property(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a,b:c").mkdir()
    (tmp_path / "a,b:c" / "package.json").write_text('{"name": "x", "license": "MIT"}', encoding="utf-8")
    (tmp_path / "CITATION.cff").write_text(CFF + "license: Apache-2.0\n", encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('manifests = ["a,b:c/package.json"]\n', encoding="utf-8")
    _, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github")
    assert out.startswith("::error file=a%2Cb%3Ac/package.json,line=1,col=15,title=")


PLAIN, RED = "codemeta.json:1:47: error[", "codemeta.json:1:47: \033[1;31merror\033[0m["


@pytest.mark.parametrize(
    ("env", "start"),
    [
        ({}, PLAIN),
        ({"FORCE_COLOR": "1"}, RED),
        ({"FORCE_COLOR": "0"}, PLAIN),
        ({"FORCE_COLOR": "1", "NO_COLOR": "1"}, PLAIN),
    ],
)
def test_colour(
    env: dict[str, str], start: str, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    assert _run(capsys, "check", "--root", str(tmp_path))[1].startswith(start)


@pytest.mark.parametrize("fmt", ["text", "github"])
def test_control_characters_are_escaped(fmt: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """A keyword holding ESC could retitle the terminal or hide lines."""
    (tmp_path / "CITATION.cff").write_text(CFF + "keywords: [a]\n", encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(keywords=["\x1b]0;x\x07\x9b"]), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", fmt)
    assert code == 1
    assert not re.search("[\x00-\x09\x0b-\x1f\x7f-\x9f]", out)
    assert "\\x1b]0;x\\x07\\x9b" in out


def test_a_non_utf8_stdout_prints_utf8(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A Windows pipe is cp1252, which can't encode a CJK title: printing it must not fail the check."""
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="\u6bdb\u6cfd\u4e1c"), encoding="utf-8")
    raw = io.BytesIO()
    monkeypatch.setattr("sys.stdout", io.TextIOWrapper(raw, encoding="cp1252"))
    assert main(["check", "--root", str(tmp_path)]) == 1
    sys.stdout.flush()
    assert "\u6bdb\u6cfd\u4e1c" in raw.getvalue().decode("utf-8")


def test_ignore_drops_findings_and_warns_when_unused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('ignore = ["name-mismatch", "doi-mismatch"]\n', encoding="utf-8")
    code, out, err = _run(capsys, "check", "--root", str(tmp_path), "--json")
    assert (code, err) == (0, "citesync: warning: ignore entry 'doi-mismatch' matched no finding\n")
    assert [f["rule"] for f in json.loads(out)["findings"]] == ["not-checked"] * 9


@pytest.mark.parametrize("zenodo", [False, True])
@pytest.mark.parametrize(
    ("cff", "expected"),
    [
        ("license: [MIT, Apache-2.0]\n", [("zenodo-license-list", "error", "license")]),
        ("license: [MIT]\n", [("zenodo-license-list", "error", "license")]),
        ("license: MIT\n", []),
        (
            "identifiers:\n  - {type: doi, value: 10.1000/paper}\nreferences:\n  - {type: article, title: t}\n",
            [("zenodo-drops-field", "warning", "identifiers"), ("zenodo-drops-field", "warning", "references")],
        ),
        ("identifiers:\n  - {type: doi, value: 10.5281/ZENODO.1}\n", []),  # Zenodo links its own records
    ],
)
def test_what_zenodo_reads_from_cff_alone(
    cff: str,
    expected: list[tuple[str, str, str]],
    zenodo: bool,  # noqa: FBT001
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    files = {"CITATION.cff": CFF + cff}
    if zenodo:  # Zenodo then reads .zenodo.json alone, so CITATION.cff can hold what it likes
        files[".zenodo.json"] = json.dumps({"title": "x"})
    report = _check_json(tmp_path, capsys, files)
    found = [(f["rule"], f["severity"], f["term"]) for f in _split(report)[0] if f["rule"].startswith("zenodo-")]
    assert found == ([] if zenodo else expected)
    assert all(f["file"] == "CITATION.cff" for f in report["findings"] if f["rule"].startswith("zenodo-"))


def test_a_blank_doi_does_not_hide_the_identifiers_doi(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "CITATION.cff": CFF + 'doi: ""\nidentifiers:\n  - {type: doi, value: 10.5281/zenodo.1}\n',
        "codemeta.json": _codemeta(identifier="https://doi.org/10.5281/zenodo.2"),
    }
    assert _triples(_split(_check_json(tmp_path, capsys, files))[0]) == [
        ("doi-mismatch", "codemeta.json", "identifier")
    ]


@pytest.mark.parametrize("term", ["name", "description"])
def test_titles_compare_in_nfc(term: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    nfc, nfd = "\u00c9conomie", "E\u0301conomie"
    cff = {"name": "title", "description": "abstract"}[term]
    files = {"CITATION.cff": CFF + f'{cff}: "{nfc}"\n', "codemeta.json": _codemeta(**{term: nfd})}
    if term == "name":
        files["CITATION.cff"] = files["CITATION.cff"].replace('title: "x"\n', "")
    assert _split(_check_json(tmp_path, capsys, files))[0] == []


def test_nested_lists_are_not_followed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """YAML aliases share one list, so ten levels of ten hold 10**10 leaves in a file of a few hundred bytes."""
    levels = ["a0: &a0 [MIT, MIT, MIT, MIT, MIT, MIT, MIT, MIT, MIT, MIT]"]
    levels += [f"a{i}: &a{i} [{', '.join([f'*a{i - 1}'] * 10)}]" for i in range(1, 10)]
    cff = CFF + "\n".join(levels) + "\nlicense: [*a9]\ndoi: [*a9]\n"
    start = time.perf_counter()
    report = _check_json(tmp_path, capsys, {"CITATION.cff": cff, ".zenodo.json": json.dumps({"title": "x"})})
    assert time.perf_counter() - start < 1
    assert _split(report)[0] == []


def test_release_dates_compare_by_day(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "CITATION.cff": CFF + "date-released: 2026-01-15\n",
        "codemeta.json": _codemeta(datePublished="2026-01-15T09:00:00Z"),
        ".zenodo.json": json.dumps({"title": "x", "publication_date": "2026-01-16"}),
    }
    report = _check_json(tmp_path, capsys, files)
    assert [(f["rule"], f["file"], f["message"]) for f in _split(report)[0]] == [
        ("date-mismatch", ".zenodo.json", "'2026-01-16', CITATION.cff has '2026-01-15'")
    ]


def _git(root: Path, *args: str) -> None:
    env = {"PATH": os.environ["PATH"], "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)  # noqa: S603, S607 - test repos only


@pytest.mark.parametrize(
    ("version", "tags", "packed", "expected"),
    [
        ("0.1.0", ["v0.1.0", "v0.2.0", "latest"], 0, "0.1.0, the newest tag is v0.2.0"),
        ("0.1.0", ["v0.1.0", "v0.2.0rc1"], 2, "0.1.0, the newest tag is v0.2.0rc1"),
        ("0.1.0", ["v0.1.0", "v0.2.0"], 1, "0.1.0, the newest tag is v0.2.0"),  # loose beside packed
        ("0.9.5", ["v0.10.0", "v0.9.0"], 0, "0.9.5, the newest tag is v0.10.0"),  # by version, not as text
        ("", ["v0.2.0"], 0, None),
        ("0.2.0", ["v0.1.0", "0.2.0"], 0, None),
        ("0.1.0", ["latest"], 0, None),
        ("0.1.0", [], 0, None),
    ],
)
def test_version_behind_the_newest_tag_warns(
    version: str,
    tags: list[str],
    packed: int,
    expected: str | None,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _git(tmp_path, "init", "-q")
    (tmp_path / "CITATION.cff").write_text(CFF + f"version: {version}\n", encoding="utf-8")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t.test", "commit", "-qm", "x")
    for i, tag in enumerate(tags, 1):  # the first `packed` tags go into packed-refs, the rest stay loose
        _git(tmp_path, "tag", tag)
        if i == packed:
            _git(tmp_path, "pack-refs", "--all")
    report = _check_json(tmp_path, capsys, {})
    found = [
        (f["file"], f["term"], f["severity"], f["message"])
        for f in report["findings"]
        if f["rule"] == "version-behind-tag"
    ]
    assert found == ([("CITATION.cff", "version", "warning", expected)] if expected else [])


def test_a_linked_worktree_reads_the_clone_tags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    clone = tmp_path / "clone"
    clone.mkdir()
    _git(clone, "init", "-q")
    (clone / "CITATION.cff").write_text(CFF + "version: 0.1.0\n", encoding="utf-8")
    _git(clone, "add", "-A")
    _git(clone, "-c", "user.name=t", "-c", "user.email=t@t.test", "commit", "-qm", "x")
    _git(clone, "tag", "v1.0.0")
    _git(clone, "worktree", "add", "-q", str(tmp_path / "wt"))
    report = _check_json(tmp_path / "wt", capsys, {})
    assert [f["message"] for f in report["findings"] if f["rule"] == "version-behind-tag"] == [
        "0.1.0, the newest tag is v1.0.0"
    ]


def test_a_subdirectory_root_reads_the_repo_tags_and_reports_repo_paths(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "CITATION.cff").write_text(CFF + "version: 1.0.0\n", encoding="utf-8")
    (pkg / ".zenodo.json").write_text(json.dumps({"title": "y"}), encoding="utf-8")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "-c", "user.name=t", "-c", "user.email=t@t.test", "commit", "-qm", "x")
    _git(tmp_path, "tag", "v3.0.0")

    _, out, _ = _run(capsys, "check", "--root", str(pkg), "--format", "sarif")
    results = json.loads(out)["runs"][0]["results"]
    uris = [(r["ruleId"], r["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]) for r in results]
    assert uris == [("name-mismatch", "pkg/.zenodo.json"), ("version-behind-tag", "pkg/CITATION.cff")]
    _, out, _ = _run(capsys, "check", "--root", str(pkg), "--format", "github")
    assert out.startswith("::error file=pkg/.zenodo.json,line=1,col=2,title=citesync name-mismatch::")


ROLE = {"@type": "Role", "schema:author": {"@id": f"https://orcid.org/{ORCID_A}"}, "roleName": "Software"}


@pytest.mark.parametrize(
    ("zenodo", "expected"),
    [
        ([{"name": "B, A", "orcid": ORCID_A, "type": "Other"}], []),
        ([{"name": "D, C", "type": "Other"}], [("contributor-mismatch", ".zenodo.json", "contributor")]),
        (
            [{"name": "B, A", "orcid": ORCID_B, "type": "Other"}],
            [("contributor-mismatch", ".zenodo.json", "contributor")],
        ),
    ],
)
def test_contributors_compare_between_files_when_cff_has_none(
    zenodo: list[dict[str, str]],
    expected: list[tuple[str, str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CITATION.cff, the source, can't list contributors, so codemeta.json and .zenodo.json agree with each other."""
    files = {
        "CITATION.cff": CFF,
        "codemeta.json": _codemeta(contributor=[*_people("A B", orcid=ORCID_A), ROLE]),  # the Role isn't a person
        ".zenodo.json": json.dumps({"title": "x", "contributors": zenodo}),
    }
    assert _triples(_split(_check_json(tmp_path, capsys, files))[0]) == expected


def test_npm_contributor_strings_are_names(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "CITATION.cff": CFF,
        "codemeta.json": _codemeta(contributor=_people("A B")),
        "package.json": json.dumps({"name": "x", "version": "1.0.0", "contributors": ["C D <c@d.example>"]}),
    }
    report = _check_json(tmp_path, capsys, files)
    assert [(f["rule"], f["message"]) for f in _split(report)[0]] == [
        ("contributor-mismatch", "'C D', codemeta.json has 'A B'")
    ]

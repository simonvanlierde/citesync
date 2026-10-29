"""`citesync check` on the fixtures, against the findings in each cases.json, plus the D2 table and exit codes."""

import json
import shutil
from importlib.metadata import version
from pathlib import Path

import jsonschema
import pytest

from citesync.cli import main
from citesync.mapping import TERMS

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


def _triples(items: list[dict]) -> list[tuple[str, str | None, str | None]]:
    return [(i["rule"], i["file"], i["term"]) for i in items]


def _split(report: dict) -> tuple[list[dict], list[dict]]:
    """The findings that fail a run, and the info."""
    findings = report["findings"]
    return [f for f in findings if f["severity"] != "info"], [f for f in findings if f["severity"] == "info"]


@pytest.mark.parametrize(("repo", "case"), CASES, ids=[f"{r}-{c['name']}" for r, c in CASES])
def test_fixture_case(repo: str, case: dict, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / repo
    shutil.copytree(FIXTURES / repo, root)
    _write_config(root, case["config"])

    code, out, err = _run(capsys, "check", "--root", str(root), "--format", "json")
    report = json.loads(out)
    jsonschema.validate(report, OUTPUT_SCHEMA)
    assert (code, err) == (case["exit"], "")
    findings, info = _split(report)
    assert _triples(findings) == _triples(case["findings"])
    assert _triples(info) == _triples(case["info"])

    # Text: one line per finding and a summary, not-checked only with -v.
    _, text, _ = _run(capsys, "check", "--root", str(root))
    assert len(text.splitlines()) == len(case["findings"]) + 1
    _, verbose, _ = _run(capsys, "check", "--root", str(root), "-v")
    assert len(verbose.splitlines()) == len(case["findings"]) + len(case["info"]) + 1


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


@pytest.mark.parametrize(("cff", "codemeta"), [("0.3.1-rc.1", "0.3.1rc1"), ("v1.2.3", "1.2.3"), ("1.0", "1.0.0")])
def test_versions_compare_as_pep440(
    cff: str, codemeta: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF + f"version: {cff}\n", encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(version=codemeta), encoding="utf-8")
    assert _run(capsys, "check", "--root", str(tmp_path)) == (0, "0 errors, 0 warnings in 2 files\n", "")
    (tmp_path / "codemeta.json").write_text(_codemeta(version="0.3.1rc2"), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path))
    assert (code, out.split(" ")[:2]) == (1, ["codemeta.json:", "error[version-mismatch]"])


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
    assert _run(capsys, "check", "--root", str(tmp_path), "--quiet")[1] == out.rsplit("5 errors", 1)[0]
    assert out.splitlines() == [
        ".zenodo.json: error[license-mismatch] license: 'apache-2.0', CITATION.cff has 'MIT'",
        ".zenodo.json: error[name-mismatch] name: 'z', CITATION.cff has 'x'",
        "codemeta.json: error[context-mismatch] @context: 4.0, configured 3.0",
        "codemeta.json: error[name-mismatch] name: 'y', CITATION.cff has 'x'",
        "codemeta.json: error[version-mismatch] version: '2.0.0', CITATION.cff has '1.0.0'",
        "5 errors, 0 warnings in 3 files",
    ]


def test_github_format(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    code, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github", "-v")
    lines = out.splitlines()
    assert code == 1
    assert lines[0] == "::error file=codemeta.json,title=citesync name-mismatch::name: 'y', CITATION.cff has 'x'"
    assert all(line.startswith("::notice title=citesync not-checked::") for line in lines[1:-1])
    assert lines[-1] == "::notice::citesync: 1 error, 0 warnings in 2 files"


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


def test_write_is_not_a_command(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["write"])
    assert exit_.value.code == 2
    assert "invalid choice: 'write'" in capsys.readouterr().err


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
    assert message in found["message"]
    assert (found["line"], found["column"]) == (position or (None, None))
    _, github, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github")
    where = f"line={position[0]},col={position[1]}," if position else ""
    assert f"::error file={name},{where}title=citesync unreadable::" in github


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
    assert {(f["file"], f["term"]) for f in info} == {("CITATION.cff", term) for term in TERMS}
    assert report["summary"] == {"files": 3, "errors": 2, "warnings": 0, "info": 8}


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
                "pyproject.toml": PYPROJECT,
                "CITATION.cff": CFF + "abstract: a\n",
                "codemeta.json": _codemeta(name="y", description="b"),
            },
            [("description-mismatch", "codemeta.json", "description"), ("name-mismatch", "codemeta.json", "name")],
            id="manifest-source-citation-names-compared-between-holders",
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
                ("keywords-mismatch", "codemeta.json", "keywords", "Life Cycle, lca, CITATION.cff has life cycle, LCA"),
                ("keywords-not-subset", "pyproject.toml", "keywords", "Lca: in pyproject.toml, not in CITATION.cff"),
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
        "pyproject.toml": _pyproject('keywords = ["Lca"]'),
    }
    report = _check_json(tmp_path, capsys, files)
    assert [(f["rule"], f["file"], f["term"], f["message"]) for f in _split(report)[0]] == expected


def test_order_and_case_do_not_matter(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    files = {
        "CITATION.cff": CFF + "keywords: [b, a]\nauthors:\n  - {given-names: Ada, family-names: Lovelace}\n",
        "codemeta.json": _codemeta(keywords=["a", "b"], author=_people("ada lovelace")),
    }
    assert _split(_check_json(tmp_path, capsys, files))[0] == []


@pytest.mark.parametrize(
    ("tree", "expected"),
    [
        ("https://github.com/example/r/tree/v1.0", []),
        (
            "https://github.com/example/s/tree/v1.0",
            ["'https://github.com/example/s/tree/v1.0', CITATION.cff has 'https://github.com/Example/R'"],
        ),
    ],
)
def test_repository_urls_compare_by_key(
    tree: str, expected: list[str], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Zenodo's GitHub integration writes the release tree URL, and GitHub paths are case-insensitive."""
    zenodo = {"title": "x", "related_identifiers": [{"relation": "isSupplementTo", "identifier": tree}]}
    files = {
        "CITATION.cff": CFF + "repository-code: https://github.com/Example/R\n",
        ".zenodo.json": json.dumps(zenodo),
    }
    assert [f["message"] for f in _split(_check_json(tmp_path, capsys, files))[0]] == expected


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
    assert report["summary"]["info"] == len(_split(report)[1]) == 7


def test_schema_lets_a_minor_release_add_rules_and_fields(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = _check_json(tmp_path, capsys, {"CITATION.cff": CFF})
    report["findings"][0] |= {"rule": "orcid-checksum", "end_line": 3}
    report["summary"]["notes"] = 0
    jsonschema.validate(report, OUTPUT_SCHEMA)
    report["findings"][0]["rule"] = "Not_Kebab"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(report, OUTPUT_SCHEMA)


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exit_:
        main(["--version"])
    assert (exit_.value.code, capsys.readouterr().out) == (0, f"citesync {version('citesync')}\n")


def test_github_format_quiet_has_no_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    _, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github", "-q")
    assert out.splitlines() == [
        "::error file=codemeta.json,title=citesync name-mismatch::name: 'y', CITATION.cff has 'x'"
    ]


def test_github_format_escapes_the_file_property(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "a,b:c").mkdir()
    (tmp_path / "a,b:c" / "package.json").write_text('{"name": "x", "license": "MIT"}', encoding="utf-8")
    (tmp_path / "CITATION.cff").write_text(CFF + "license: Apache-2.0\n", encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('manifests = ["a,b:c/package.json"]\n', encoding="utf-8")
    _, out, _ = _run(capsys, "check", "--root", str(tmp_path), "--format", "github")
    assert out.startswith("::error file=a%2Cb%3Ac/package.json,title=")


PLAIN, RED = "codemeta.json: error[", "codemeta.json: \033[1;31merror\033[0m["


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


def test_ignore_drops_findings_and_warns_when_unused(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    (tmp_path / "codemeta.json").write_text(_codemeta(name="y"), encoding="utf-8")
    (tmp_path / "citesync.toml").write_text('ignore = ["name-mismatch", "doi-mismatch"]\n', encoding="utf-8")
    code, out, err = _run(capsys, "check", "--root", str(tmp_path), "--json")
    assert (code, err) == (0, "citesync: warning: ignore entry 'doi-mismatch' matched no finding\n")
    assert [f["rule"] for f in json.loads(out)["findings"]] == ["not-checked"] * 7

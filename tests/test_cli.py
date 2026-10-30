"""What the command line prints: the text report, its hints, and each message on stderr."""

import json
import shutil
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from citesync.cli import main

if TYPE_CHECKING:
    from tests.conftest import Run

FIXTURES = Path(__file__).parent / "fixtures"
SYNTHETIC = FIXTURES / "synthetic-agree"
PLANTED = Path(__file__).parent / "write" / "planted"
CFF = 'cff-version: 1.2.0\nmessage: "m"\ntitle: "x"\n'
CODEMETA = json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "y"})


def _repo(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(exist_ok=True)
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return root


def _planted(root: Path) -> Path:
    shutil.copytree(SYNTHETIC, root)
    for name in ("codemeta.json", ".zenodo.json", "pyproject.toml", "package.json"):
        shutil.copy(PLANTED / name, root / name)
    (root / "citesync.toml").write_text('write-manifests = ["version"]\n', encoding="utf-8")
    return root


FIX = "Make the file agree with the source, or the other way round if the source is wrong."
# 15 errors planted in four files; write fixes the 9 that write-manifests lets it.
CHECK_SNAPSHOT = f"""\
.zenodo.json:6:3: error[author-mismatch] author: 'Alan Turing; Ada Lovelace (0000-0002-1825-0097)', CITATION.cff has 'Ada Lovelace (0000-0002-1825-0097); Alan Turing'
  help: {FIX}
.zenodo.json:22:3: error[date-mismatch] datePublished: '2025-12-01', CITATION.cff has '2026-01-15'
  help: {FIX}
.zenodo.json:21:3: error[license-mismatch] license: 'mit', CITATION.cff has 'Apache-2.0'
  help: {FIX}
.zenodo.json:23:3: error[repository-mismatch] codeRepository: 'https://github.com/example/other', CITATION.cff has 'https://github.com/example/synthagree'
  help: {FIX}
codemeta.json:11:3: error[author-mismatch] author: 'Ada Lovelace (0000-0001-5109-3700); Alan Turing', CITATION.cff has 'Ada Lovelace (0000-0002-1825-0097); Alan Turing'
  help: {FIX}
codemeta.json:24:3: error[keywords-mismatch] keywords: missing delta (compared with CITATION.cff)
  help: {FIX}
codemeta.json:6:3: error[version-mismatch] version: '1.2.4', CITATION.cff has '1.2.3'
  help: {FIX}
package.json:5:3: error[author-mismatch] author: 'Alan Turing', CITATION.cff has 'Ada Lovelace (0000-0002-1825-0097); Alan Turing'
  help: {FIX}
package.json:12:3: error[keywords-not-subset] keywords: zeta: in package.json, not in CITATION.cff
  help: Add the keyword to the citation file, or remove it from the manifest.
package.json:8:3: error[repository-mismatch] codeRepository: 'https://github.com/example/other', CITATION.cff has 'https://github.com/example/synthagree'
  help: {FIX}
package.json:3:3: error[version-mismatch] version: '1.2.4', CITATION.cff has '1.2.3'
  help: {FIX}
pyproject.toml:12:1: error[keywords-not-subset] keywords: zeta: in pyproject.toml, not in CITATION.cff
  help: Add the keyword to the citation file, or remove it from the manifest.
pyproject.toml:11:1: error[license-mismatch] license: 'MIT', CITATION.cff has 'Apache-2.0'
  help: {FIX}
pyproject.toml:15:1: error[repository-mismatch] codeRepository: 'https://github.com/example/other', CITATION.cff has 'https://github.com/example/synthagree'
  help: {FIX}
pyproject.toml:7:1: error[version-mismatch] version: '1.2.4', CITATION.cff has '1.2.3'
  help: {FIX}
15 errors, 0 warnings in 6 files
9 fixable with `citesync write`
"""  # noqa: E501
WRITE_SNAPSHOT = f"""\
wrote .zenodo.json
wrote codemeta.json
wrote package.json
wrote pyproject.toml
package.json:5:3: error[author-mismatch] author: 'Alan Turing', CITATION.cff has 'Ada Lovelace (0000-0002-1825-0097); Alan Turing' (edit it by hand, or add author to write-manifests)
  help: {FIX}
package.json:12:3: error[keywords-not-subset] keywords: zeta: in package.json, not in CITATION.cff (edit it by hand, or add keywords to write-manifests)
  help: Add the keyword to the citation file, or remove it from the manifest.
package.json:8:3: error[repository-mismatch] codeRepository: 'https://github.com/example/other', CITATION.cff has 'https://github.com/example/synthagree' (edit it by hand, or add codeRepository to write-manifests)
  help: {FIX}
pyproject.toml:12:1: error[keywords-not-subset] keywords: zeta: in pyproject.toml, not in CITATION.cff (edit it by hand, or add keywords to write-manifests)
  help: Add the keyword to the citation file, or remove it from the manifest.
pyproject.toml:11:1: error[license-mismatch] license: 'MIT', CITATION.cff has 'Apache-2.0' (edit it by hand, or add license to write-manifests)
  help: {FIX}
pyproject.toml:15:1: error[repository-mismatch] codeRepository: 'https://github.com/example/other', CITATION.cff has 'https://github.com/example/synthagree' (edit it by hand, or add codeRepository to write-manifests)
  help: {FIX}
9 fixed, 6 left in 6 files
"""  # noqa: E501


def test_check_and_write_text_snapshot(tmp_path: Path, run: "Run") -> None:
    root = _planted(tmp_path / "repo")
    assert run("check", "--root", str(root)) == (1, CHECK_SNAPSHOT, "")
    assert run("write", "--root", str(root)) == (1, WRITE_SNAPSHOT, "")


def test_help_line_in_github_and_sarif(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, {"CITATION.cff": CFF, "codemeta.json": CODEMETA})
    help_ = "Make the file agree with the source, or the other way round if the source is wrong."
    out = run("check", "--root", str(root), "--format", "github")[1]
    assert out.splitlines()[0].endswith(f"::name: 'y', CITATION.cff has 'x'%0Ahelp: {help_}")
    driver = json.loads(run("check", "--root", str(root), "--format", "sarif")[1])["runs"][0]["tool"]
    assert driver["driver"]["rules"][0]["help"] == {"text": help_}


def test_fixable_count_only_when_check_fails(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, {"CITATION.cff": CFF, "codemeta.json": CODEMETA})
    assert run("check", "--root", str(root))[1].endswith(
        "1 error, 0 warnings in 2 files\n1 fixable with `citesync write`\n"
    )
    assert run("check", "-q", "--root", str(root))[1].count("fixable") == 0
    (root / "codemeta.json").write_text(CODEMETA.replace('"y"', '"x"'), encoding="utf-8")
    assert run("check", "--root", str(root)) == (0, "0 errors, 0 warnings in 2 files\n", "")


def test_counts_leave_out_a_licence_list_write_cannot_fix(tmp_path: Path, run: "Run") -> None:
    """A rewritten CITATION.cff doesn't make its zenodo-license-list error count as fixed."""
    cff = 'cff-version: 1.2.0\nmessage: "m"\ntitle: "y"\nversion: 1.0.0\nlicense:\n  - MIT\n  - Apache-2.0\n'
    spdx = ["https://spdx.org/licenses/MIT", "https://spdx.org/licenses/Apache-2.0"]
    codemeta = json.dumps({**json.loads(CODEMETA), "version": "2.0.0", "license": spdx})
    files = {"CITATION.cff": cff, "codemeta.json": codemeta, "citesync.toml": 'source = "codemeta.json"\n'}
    root = _repo(tmp_path, files)
    assert run("check", "--root", str(root))[1].endswith("\n1 fixable with `citesync write`\n")
    assert run("write", "--root", str(root))[1].endswith("\n1 fixed, 1 left in 2 files\n")


def test_a_missing_source_names_the_root(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, {"codemeta.json": CODEMETA})
    assert run("check", "--root", str(root)) == (
        2,
        "",
        (
            f"citesync: CITATION.cff: the source file is missing from {root}; name another with --source,"
            " or the repo with --root\n"
        ),
    )


def test_root_must_be_a_directory(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (tmp_path / "CITATION.cff").write_text(CFF, encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        main(["check", "--root", str(tmp_path / "CITATION.cff")])
    assert exc.value.code == 2
    assert capsys.readouterr().err.endswith(f"argument --root: not a directory: {tmp_path / 'CITATION.cff'}\n")


def test_the_walk_falls_back_to_the_git_top(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run: "Run") -> None:
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    monkeypatch.chdir(tmp_path / "src")
    assert run("config")[1].startswith(f"# root: {tmp_path}\n")


@pytest.mark.skipif(sys.version_info < (3, 14), reason="argparse suggests from Python 3.14")
def test_a_mistyped_choice_gets_a_suggestion(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["check", "--format", "sarf"])
    assert "maybe you meant 'sarif'?" in capsys.readouterr().err


def test_explain_suggests_a_rule(run: "Run") -> None:
    assert run("explain", "version-mismatc") == (
        2,
        "",
        "citesync: unknown rule 'version-mismatc'; `citesync rules` lists them; did you mean 'version-mismatch'?\n",
    )


@pytest.mark.parametrize(
    ("config", "message"),
    [
        (
            'ignore = ["name-mismatch", "version"]\n',
            (
                "citesync.toml: ignore entry 'version' is not a rule id; `citesync rules` lists them;"
                " did you mean 'version-mismatch'?"
            ),
        ),
        ('ignore = ["unreadable"]\n', "citesync.toml: ignore entry 'unreadable' can't be ignored"),
        ("codemeta-version = 3.0\n", 'citesync.toml: codemeta-version must be a string, such as "3.0"'),
        ('write-manifests = ["repository"]\n', "citesync.toml: write-manifests: 'repository' is codeRepository here"),
        (
            'write-manifests = ["keyword"]\n',
            "citesync.toml: write-manifests: 'keyword' is not a term; it takes 'all' or version, author, contributor,",
        ),
        ('write-manifests = ["name"]\n', "citesync.toml: write-manifests: 'name' is never written to a manifest"),
    ],
)
def test_bad_config_messages(config: str, message: str, tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, {"CITATION.cff": CFF, "citesync.toml": config})
    code, out, err = run("check", "--root", str(root))
    assert (code, out) == (2, "")
    assert err.startswith(f"citesync: {message}")


def test_write_manifests_all_means_the_manifest_fields(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, {"citesync.toml": 'write-manifests = "all"\n'})
    assert (
        'write-manifests = ["version", "author", "contributor", "license", "codeRepository", "keywords"]\n'
        in (run("config", "--root", str(root))[1])
    )


def test_the_unused_ignore_warning_is_quiet_under_q(tmp_path: Path, run: "Run") -> None:
    root = _repo(tmp_path, {"CITATION.cff": CFF, "citesync.toml": 'ignore = ["doi-mismatch"]\n'})
    assert run("check", "-q", "--root", str(root)) == (0, "", "")
    assert run("check", "--root", str(root))[2] == (
        "citesync: warning: ignore entry 'doi-mismatch' matched no finding\n"
    )


def test_diff_counts_on_stderr(tmp_path: Path, run: "Run") -> None:
    root = _planted(tmp_path / "repo")
    code, out, err = run("write", "--diff", "--root", str(root))
    assert (code, err) == (1, "would fix 9 findings in 4 files\n")
    assert out.startswith("--- a/")


def test_verbose_names_a_skipped_manifest(tmp_path: Path, run: "Run") -> None:
    root = _repo(
        tmp_path,
        {"CITATION.cff": CFF, "pyproject.toml": '[project]\nname = "x"\n', "package.json": '{"private": true}'},
    )
    lines = run("check", "-v", "--root", str(root))[1].splitlines()
    assert 'package.json: info[manifest-skipped] "private": true, so it is never published' in lines
    assert "pyproject.toml: info[manifest-skipped] no [build-system], so it isn't a package" in lines
    assert "manifest-skipped" not in run("check", "--root", str(root))[1]


@pytest.mark.parametrize(
    ("flag", "env", "coloured"),
    [("never", {"FORCE_COLOR": "1"}, False), ("always", {"NO_COLOR": "1"}, True), ("auto", {"FORCE_COLOR": "1"}, True)],
)
def test_color_flag_wins_over_the_environment(
    flag: str,
    env: dict[str, str],
    coloured: bool,  # noqa: FBT001
    tmp_path: Path,
    run: "Run",
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    root = _repo(tmp_path, {"CITATION.cff": CFF, "codemeta.json": CODEMETA})
    assert ("\033[" in run("check", "--color", flag, "--root", str(root))[1]) is coloured


def test_short_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["-V"])
    assert (exc.value.code, capsys.readouterr().out.startswith("citesync ")) == (0, True)


def test_keyword_findings_name_the_missing_and_extra_words(tmp_path: Path, run: "Run") -> None:
    codemeta = json.dumps({"@context": "https://w3id.org/codemeta/3.0", "name": "x", "keywords": ["a", "c", "big-d"]})
    root = _repo(tmp_path, {"CITATION.cff": CFF + "keywords: [a, b, big d]\n", "codemeta.json": codemeta})
    report = json.loads(run("check", "--json", "--root", str(root))[1])
    assert [f["message"] for f in report["findings"] if f["rule"] == "keywords-mismatch"] == [
        "missing b; extra c; 'big-d' differs from 'big d' only in separators (compared with CITATION.cff)"
    ]

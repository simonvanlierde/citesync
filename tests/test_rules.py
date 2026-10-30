"""`citesync rules` and `explain`, and docs/rules.md and the output schema kept in step with the rules."""

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

from citesync.cli import main
from citesync.rules import RULES, markdown

ROOT = Path(__file__).parent.parent


def test_rules_doc_is_current() -> None:
    assert (ROOT / "docs" / "rules.md").read_text(encoding="utf-8") == markdown(), (
        "docs/rules.md is out of date: uv run python -m citesync.rules > docs/rules.md"
    )


def test_output_schema_admits_every_rule() -> None:
    schema = json.loads((ROOT / "tests" / "output.schema.json").read_text(encoding="utf-8"))
    pattern = re.compile(schema["$defs"]["finding"]["properties"]["rule"]["pattern"])
    assert all(pattern.match(rule) for rule in RULES)


def test_rules_lists_every_rule(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["rules"]) == 0
    assert [line.split()[:2] for line in capsys.readouterr().out.splitlines()] == [
        [rule, r.severity] for rule, r in RULES.items()
    ]
    assert main(["rules", "--format", "json"]) == 0
    rules = json.loads(capsys.readouterr().out)
    assert [r["rule"] for r in rules] == list(RULES)
    assert rules[-1]["url"].endswith("docs/rules.md#not-checked")


def test_explain(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["explain", "unreadable"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("## unreadable\n\n")
    assert out in markdown()
    assert main(["explain", "nope"]) == 2
    assert capsys.readouterr() == ("", "citesync: unknown rule 'nope'; `citesync rules` lists them\n")


def test_runs_as_a_module() -> None:
    run = subprocess.run([sys.executable, "-m", "citesync", "rules"], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert "keywords-not-subset" in run.stdout


def test_check_leaves_slow_imports_alone(tmp_path: Path) -> None:
    # Each costs 2 to 10 ms a run, and check needs none of them here: the writer and its tomlkit,
    # the package metadata behind --version, importlib.resources, shutil (argparse's help
    # width), and packaging and urllib.parse, since the versions and URLs match as written. Key positions
    # are read only for a finding.
    (tmp_path / "CITATION.cff").write_text('cff-version: 1.2.0\nmessage: m\ntitle: x\nversion: "1.0"\n', "utf-8")
    (tmp_path / "codemeta.json").write_text(
        '{"@context": "https://w3id.org/codemeta/3.0", "name": "x", "version": "1.0"}', "utf-8"
    )
    code = (
        "import sys; from citesync.cli import main; code = main(['check', '-q']);"
        " print(code, sorted(m for m in ('citesync.write', 'tomlkit', 'importlib.metadata', 'importlib.resources',"
        " 'shutil', 'packaging.version', 'difflib', 'urllib.parse', 'citesync.positions') if m in sys.modules))"
    )
    run = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=tmp_path)  # noqa: S603
    assert run.stdout.splitlines()[-1] == "0 []", run.stdout + run.stderr

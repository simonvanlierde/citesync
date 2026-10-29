"""`citesync rules` and `explain`, and docs/rules.md and the output schema kept in step with the rules."""

import json
from pathlib import Path

import pytest

from citesync.cli import main
from citesync.rules import RULES, markdown

ROOT = Path(__file__).parent.parent


def test_rules_doc_is_current() -> None:
    assert (ROOT / "docs" / "rules.md").read_text(encoding="utf-8") == markdown(), (
        "docs/rules.md is out of date: uv run python -m citesync.rules > docs/rules.md"
    )


def test_output_schema_lists_every_rule() -> None:
    schema = json.loads((ROOT / "tests" / "output.schema.json").read_text(encoding="utf-8"))
    assert schema["$defs"]["finding"]["properties"]["rule"]["enum"] == list(RULES)


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

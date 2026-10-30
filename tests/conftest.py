"""Shared fixtures."""

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from citesync.cli import main

Edit = Callable[[dict], None]
Run = Callable[..., tuple[int, str, str]]
_UPDATES: dict[Path, list[Edit]] = {}


@pytest.fixture(autouse=True)
def _no_colour_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text output is compared as plain text, whatever the shell running the tests sets."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Run:
    """``citesync`` with these arguments, returning its exit code, stdout and stderr."""

    def call(*args: str) -> tuple[int, str, str]:
        code = main(list(args))
        out, err = capsys.readouterr()
        return code, out, err

    return call


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-expected",
        action="store_true",
        help="Rewrite the expected cases.json and record.json under tests/fixtures from actual output.",
    )


@pytest.fixture
def update_expected(request: pytest.FixtureRequest) -> Callable[[Path, Edit], bool]:
    """Queue an edit of an expected JSON file when ``--update-expected`` is set.

    Returns True when it queued the edit, and the test then skips its assertions.
    The files are rewritten at the end of the run, in the layout they have now,
    so the change reads as a small git diff.
    """

    def queue(path: Path, edit: Edit) -> bool:
        if not request.config.getoption("--update-expected"):
            return False
        _UPDATES.setdefault(path, []).append(edit)
        return True

    return queue


def pytest_sessionfinish() -> None:
    for path, edits in _UPDATES.items():
        data = json.loads(path.read_text(encoding="utf-8"))
        for edit in edits:
            edit(data)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

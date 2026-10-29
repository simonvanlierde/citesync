"""Shared fixtures."""

import pytest


@pytest.fixture(autouse=True)
def _no_colour_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Text output is compared as plain text, whatever the shell running the tests sets."""
    monkeypatch.delenv("FORCE_COLOR", raising=False)
    monkeypatch.delenv("NO_COLOR", raising=False)

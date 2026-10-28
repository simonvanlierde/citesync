"""Smoke test: replace with real tests."""

import citesync


def test_imports() -> None:
    """The package imports."""
    assert citesync.__name__ == "citesync"

"""The docs that list the compared fields name every one of them."""

from pathlib import Path

import pytest

from citesync.mapping import TERMS

DOCS = Path(__file__).parent.parent / "docs"
FIELD_LISTS = ["config.md"]


@pytest.mark.parametrize("name", FIELD_LISTS)
@pytest.mark.parametrize("term", TERMS)
def test_field_list_names_every_term(name: str, term: str) -> None:
    assert f"`{term}`" in (DOCS / name).read_text(encoding="utf-8")

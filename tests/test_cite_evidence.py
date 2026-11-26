"""OpenAlex evidence retains source claims without assigning them to citation authors."""

import json
from collections.abc import Callable

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from citesync.cite_evidence import openalex_evidence
from citesync.errors import CheckError

API = "https://api.openalex.org/works/W1234"
TEXT_OR_NULL = st.text() | st.none()


def _request(work: object, references: object) -> Callable[[str], bytes]:
    replies = {API: work, f"{API}/references": references}
    return lambda url: json.dumps(replies[url]).encode()


def test_preserves_work_and_author_identity() -> None:
    work = {
        "id": "https://openalex.org/W1234",
        "doi": "https://doi.org/10.5555/example",
        "primary_location": {"landing_page_url": "https://arxiv.org/abs/2411.01234v2"},
        "authorships": [
            {
                "author": {
                    "id": "https://openalex.org/A1000",
                    "orcid": "https://orcid.org/0000-0002-1825-0097",
                },
                "raw_author_name": "J. Carberry",
                "contributor_roles": [
                    {"id": "https://openalex.org/contributor-roles/software", "display_name": "Software"},
                ],
            },
            {
                "author": {"id": None, "orcid": None},
                "raw_author_name": "J. Carberry",
                "contributor_roles": [
                    {"id": "https://openalex.org/contributor-roles/editor", "display_name": "Editor"},
                ],
            },
        ],
    }
    result = openalex_evidence("https://openalex.org/W1234", _request(work, {"references": []}))
    assert result == {
        "provider": "openalex",
        "work_id": "W1234",
        "doi": "https://doi.org/10.5555/example",
        "primary_location": {"landing_page_url": "https://arxiv.org/abs/2411.01234v2"},
        "authorships": [
            {
                "author_id": "https://openalex.org/A1000",
                "orcid": "https://orcid.org/0000-0002-1825-0097",
                "raw_author_name": "J. Carberry",
                "contributor_roles": [
                    {"id": "https://openalex.org/contributor-roles/software", "display_name": "Software"},
                ],
            },
            {
                "author_id": None,
                "orcid": None,
                "raw_author_name": "J. Carberry",
                "contributor_roles": [
                    {"id": "https://openalex.org/contributor-roles/editor", "display_name": "Editor"},
                ],
            },
        ],
        "references": [],
    }


@given(st.lists(st.tuples(TEXT_OR_NULL, TEXT_OR_NULL, TEXT_OR_NULL)))
@example([("A printed line", None, None), (None, "https://doi.org/10.5555/cited", "https://openalex.org/W42")])
def test_keeps_reference_lines_in_order(
    lines: list[tuple[str | None, str | None, str | None]],
) -> None:
    # A source DOI and OpenAlex match are independent, and duplicate matches are allowed.
    references = [{"raw_reference_string": raw, "raw_doi": doi, "work_id": matched} for raw, doi, matched in lines]
    work = {"id": "https://openalex.org/W1234", "authorships": []}
    result = openalex_evidence("W1234", _request(work, {"references": references}))
    assert result["references"] == references


@pytest.mark.parametrize(
    "work_id",
    ["https://example.org/W1234", "https://openalex.org/W1234?x=1", "W1234/references", "A1234", "W"],
)
def test_refuses_other_request_targets(work_id: str) -> None:
    def no_request(url: str) -> bytes:
        pytest.fail(f"unexpected request to {url}")

    with pytest.raises(CheckError, match="OpenAlex work ID"):
        openalex_evidence(work_id, no_request)


def test_refuses_a_different_work() -> None:
    with pytest.raises(CheckError, match="W1234"):
        openalex_evidence(
            "W1234",
            _request({"id": "https://openalex.org/W1", "authorships": []}, {}),
        )


def test_refuses_an_invalid_role_id() -> None:
    work = {
        "id": "https://openalex.org/W1234",
        "authorships": [{"author": {"id": "https://openalex.org/A1000"}, "contributor_roles": [{"id": 2}]}],
    }
    with pytest.raises(CheckError, match=r"contributor_roles.*id"):
        openalex_evidence("W1234", _request(work, {"references": []}))


def test_refuses_invalid_json() -> None:
    with pytest.raises(CheckError, match=r"OpenAlex.*JSON"):
        openalex_evidence("W1234", lambda _url: b"\xff")


def test_refuses_an_invalid_reference() -> None:
    work = {"id": "https://openalex.org/W1234", "authorships": []}
    with pytest.raises(CheckError, match=r"references.*raw_doi"):
        openalex_evidence("W1234", _request(work, {"references": [{"raw_doi": True}]}))

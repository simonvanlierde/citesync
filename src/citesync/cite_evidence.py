"""Read attribution and reference evidence for one OpenAlex work."""

import json
import re
from collections.abc import Callable

from citesync.errors import CheckError

_WORK_PREFIX = "https://openalex.org/"
_API = "https://api.openalex.org/works"
_WORK_ID = re.compile(r"W[0-9]{1,20}")


def work_id(value: str) -> str | None:
    """An explicit OpenAlex work ID, with or without its public URL."""
    bare = value.removeprefix(_WORK_PREFIX)
    return bare if _WORK_ID.fullmatch(bare) else None


def openalex_work(work: str, request: Callable[[str], bytes]) -> dict[str, object]:
    """Read an explicitly selected OpenAlex work and verify its identity."""
    record = _response(request, f"{_API}/{work}")
    identity = _nullable_text(record, "id", "work")
    if identity is None or work_id(identity) != work:
        msg = f"OpenAlex returned another work or no ID for {work}"
        raise CheckError(msg)
    return record


def openalex_evidence(work: str, request: Callable[[str], bytes]) -> dict[str, object]:
    """Read a work and its reference list, keeping claims scoped to their provider and work."""
    if (canonical := work_id(work)) is None:
        msg = "expected an OpenAlex work ID such as W1234 or https://openalex.org/W1234"
        raise CheckError(msg)
    record = openalex_work(canonical, request)
    doi = _nullable_text(record, "doi", "work")
    location = record.get("primary_location")
    landing_page = (
        _nullable_text(_object(location, "primary_location"), "landing_page_url", "primary_location")
        if location is not None
        else None
    )
    authorships = [_authorship(item) for item in _array(record.get("authorships"), "authorships")]
    references = _array(_response(request, f"{_API}/{canonical}/references").get("references"), "references")
    return {
        "provider": "openalex",
        "work_id": canonical,
        "doi": doi,
        "primary_location": {"landing_page_url": landing_page} if location is not None else None,
        "authorships": authorships,
        "references": [_reference(item) for item in references],
    }


def _authorship(item: object) -> dict[str, object]:
    authorship = _object(item, "authorships entry")
    identity = authorship.get("author")
    author = _object(identity, "authorships.author") if identity is not None else {}
    roles = _array(authorship.get("contributor_roles", []), "authorships.contributor_roles")
    return {
        "author_id": _nullable_text(author, "id", "authorships.author"),
        "orcid": _nullable_text(author, "orcid", "authorships.author"),
        "raw_author_name": _nullable_text(authorship, "raw_author_name", "authorships"),
        "contributor_roles": [_role(item) for item in roles],
    }


def _role(item: object) -> dict[str, str | None]:
    field = "authorships.contributor_roles"
    role = _object(item, field)
    identity = _nullable_text(role, "id", field)
    if not identity:
        msg = f"OpenAlex {field}.id is missing"
        raise CheckError(msg)
    return {"id": identity, "display_name": _nullable_text(role, "display_name", field)}


def _reference(item: object) -> dict[str, str | None]:
    reference = _object(item, "references entry")
    return {key: _nullable_text(reference, key, "references") for key in ("raw_reference_string", "raw_doi", "work_id")}


def _response(request: Callable[[str], bytes], url: str) -> dict[str, object]:
    content = request(url)
    try:
        parsed = json.loads(content)
    except (ValueError, RecursionError) as error:
        msg = "OpenAlex returned invalid JSON"
        raise CheckError(msg) from error
    return _object(parsed, "response")


def _object(value: object, field: str) -> dict[str, object]:
    if not isinstance(value, dict):
        msg = f"OpenAlex {field} is not an object"
        raise CheckError(msg)
    return value


def _array(value: object, field: str) -> list[object]:
    if not isinstance(value, list):
        msg = f"OpenAlex {field} is not a list"
        raise CheckError(msg)
    return value


def _nullable_text(obj: dict[str, object], key: str, field: str) -> str | None:
    value = obj.get(key)
    if value is not None and not isinstance(value, str):
        msg = f"OpenAlex {field}.{key} is not text or null"
        raise CheckError(msg)
    return value

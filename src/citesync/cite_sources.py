"""Resolve exact identifiers through public citation metadata providers."""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, unquote, urlsplit

from citesync import codecs
from citesync.cite_evidence import openalex_work, work_id
from citesync.errors import CheckError
from citesync.formats import (
    Person,
    _adapt,
    _detect_version,
    _read_term,
    codemeta_is_dataset,
    codemeta_type_key,
    parse_data,
    person,
)
from citesync.mapping import EXPORT_TERMS, TERMS, Mapping, resolve

if TYPE_CHECKING:
    from citesync.cite_http import Responses

_DOI = re.compile(r"10\.\d{4,9}/[^\s\x00-\x1f\x7f]{1,300}", re.ASCII)
_DOI_PREFIX = re.compile(r"(?:https?://)?(?:www\.)?(?:dx\.)?doi\.org/|doi:\s*", re.IGNORECASE)
_ARXIV = re.compile(r"(?P<id>(?:\d{4}\.\d{4,5}|[a-z][a-z0-9.-]*/\d{7}))(?P<version>v[1-9]\d*)?", re.IGNORECASE)
_ARXIV_PREFIX = re.compile(r"(?:https?://(?:www\.)?arxiv\.org/(?:abs|pdf)/|arxiv:\s*)", re.IGNORECASE)
_REPO = re.compile(r"https?://(?:www\.)?github\.com/([A-Za-z0-9-]{1,39})/([A-Za-z0-9_.-]{1,100})/?", re.IGNORECASE)
_SHA = re.compile(r"[0-9a-f]{40}")
_ORCID = re.compile(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]")
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_ATOM = "{http://www.w3.org/2005/Atom}"
_TYPES = {
    "Software": "software",
    "SoftwareSourceCode": "software",
    "software": "software",
    "Dataset": "dataset",
    "dataset": "dataset",
    "JournalArticle": "article",
    "ConferencePaper": "conference",
    "ScholarlyArticle": "article",
    "journal-article": "article",
    "proceedings-article": "conference",
    "article": "article",
    "conference-paper": "conference",
    "Preprint": "preprint",
    "posted-content": "preprint",
    "preprint": "preprint",
}
_EXTRAS = {
    "url": "url",
    "containerTitle": "containerTitle",
    "volume": "volume",
    "issue": "issue",
    "pagination": "pages",
    "primaryCategory": "primaryCategory",
}


@dataclass(frozen=True)
class Identifier:
    """An identifier parsed before dispatch to a fixed provider."""

    provider: str
    value: str


def doi(value: object) -> str | None:
    """Normalize resolver input, preserving case and percent escapes in bare DOIs."""
    if not isinstance(value, str):
        return None
    value = value.strip()
    prefix = _DOI_PREFIX.match(value)
    if prefix:
        suffix = value[prefix.end() :]
        if not prefix[0].lower().startswith("doi:"):
            suffix = suffix.split("#", 1)[0].split("?", 1)[0]
        try:
            value = unquote(suffix, errors="strict").strip()
        except UnicodeDecodeError:
            return None
    return value if _DOI.fullmatch(value) and all(c.isprintable() for c in value) else None


def arxiv_id(value: str) -> str | None:
    """Read a bare, prefixed, abstract or PDF arXiv identifier."""
    value = _ARXIV_PREFIX.sub("", value.strip(), count=1)
    value = value.split("#", 1)[0].split("?", 1)[0].removesuffix(".pdf")
    return value if _ARXIV.fullmatch(value) and len(value) <= 100 else None


def identifier(value: str) -> Identifier:
    """Recognize a DOI, arXiv ID or a public GitHub repository URL."""
    if canonical := doi(value):
        return Identifier("doi", canonical)
    if canonical := arxiv_id(value):
        return Identifier("arxiv", canonical)
    if canonical := work_id(value.strip()):
        return Identifier("openalex", canonical)
    if match := _REPO.fullmatch(value.strip()):
        repo = match[2].removesuffix(".git")
        if repo not in {"", ".", ".."}:
            return Identifier("github", f"{match[1].lower()}/{repo.lower()}")
    msg = "use a DOI, an arXiv ID or URL, a public GitHub repository URL, or an OpenAlex work ID"
    raise ValueError(msg)


@dataclass(frozen=True)
class Work:
    """A typed citation and the identities kept apart from its written fields."""

    kind: str
    record: dict[str, Any]
    source: str
    revision: str | None = None
    related: dict[str, object] = field(default_factory=dict)
    preferred: Work | None = None
    preferred_issue: str | None = None
    attribution: tuple[dict[str, object], ...] = ()


def _object(value: object, source: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        msg = f"{source}: expected a metadata object"
        raise CheckError(msg)
    return value


def _json(body: bytes, source: str) -> Any:  # noqa: ANN401 - the provider's JSON shape is validated by its caller
    try:
        data = json.loads(body)
        json.dumps(data, ensure_ascii=False, allow_nan=False).encode()
    except (ValueError, UnicodeError, RecursionError) as err:
        msg = f"{source}: invalid JSON metadata"
        raise CheckError(msg) from err
    return data


def _field(mapping: Mapping, fmt: str, key: str, data: dict[str, Any]) -> list[Any]:
    path = mapping.get((fmt, key))
    return resolve(data, path) if path else []


def _value(mapping: Mapping, fmt: str, key: str, data: dict[str, Any]) -> Any:  # noqa: ANN401 - provider field
    return next((v for v in _field(mapping, fmt, key, data) if v not in (None, "", [])), None)


def _checked_orcid(person: Person) -> Person:
    orcid = person.orcid
    if orcid and _ORCID.fullmatch(orcid):
        digits = orcid.replace("-", "")
        total = 0
        for digit in digits[:-1]:
            total = (total + int(digit)) * 2
        if digits[-1] == "0123456789X"[(12 - total % 11) % 11]:
            return person
    return replace(person, orcid=None) if orcid else person


def _safe_text(value: str) -> str:
    return codecs.clean(_CONTROL.sub(" ", value))


def _safe_person(value: Person) -> Person:
    return _checked_orcid(
        replace(
            value,
            name=_safe_text(value.name) if value.name else None,
            given=_safe_text(value.given) if value.given else None,
            family=_safe_text(value.family) if value.family else None,
        )
    )


def _publication_date(raw: object) -> str | None:
    if isinstance(raw, list) and raw and isinstance(parts := raw[0], list) and 1 <= len(parts) <= 3:
        if any(type(part) is not int or not 0 < part < 10_000 for part in parts):
            return None
        year, *rest = parts
        return "-".join([f"{year:04d}", *(f"{n:02d}" for n in rest)])
    return codecs.date_decode(raw)


def _record(fmt: str, data: dict[str, Any], mapping: Mapping) -> dict[str, Any]:
    record: dict[str, Any] = {
        term: value
        for term in TERMS + EXPORT_TERMS
        if term not in {"name", "description", "datePublished"}
        and (path := mapping.get((fmt, term)))
        and (value := _read_term(fmt, term, data, path, mapping)) is not None
    }
    if date := _publication_date(_value(mapping, fmt, "datePublished", data)):
        record["datePublished"] = date
    for term in ("author", "contributor"):
        if people := record.get(term):
            record[term] = tuple(cleaned for p in people if (cleaned := _safe_person(p)).name)
    if keywords := record.get("keywords"):
        record["keywords"] = tuple(cleaned for word in keywords if (cleaned := _safe_text(word)))
    record.update(
        {
            key: text
            for term, key in {"name": "name", "description": "description", **_EXTRAS}.items()
            if isinstance(raw := _value(mapping, fmt, term, data), str) and (text := codecs.clean(raw))
        }
    )
    if fmt == "cff-preferred":
        pages = [str(p) for p in _field(mapping, fmt, "pagination", data) if isinstance(p, (str, int))]
        if pages:
            record["pages"] = "-".join(pages)
    return {k: _safe_text(v) if isinstance(v, str) else v for k, v in record.items()}


def _kind(raw: object, source: str) -> str:
    if isinstance(raw, list):
        known = {_TYPES[r.split("/")[-1]] for r in raw if isinstance(r, str) and r.split("/")[-1] in _TYPES}
        if len(known) == 1:
            return known.pop()
    if isinstance(raw, str) and (kind := _TYPES.get(raw.split("/")[-1])):
        return kind
    msg = f"{source}: citation metadata does not identify a supported resource type"
    raise CheckError(msg)


def _require_title(record: dict[str, Any], source: str) -> None:
    if not record.get("name"):
        msg = f"{source}: citation metadata has no title"
        raise CheckError(msg)


def _doi_work(value: str, http: Responses, mapping: Mapping) -> Work:
    quoted = quote(value, safe="")
    crossref = f"https://api.crossref.org/works/{quoted}"
    datacite = f"https://api.datacite.org/dois/{quoted}"
    if (body := http.get(crossref)) is not None:
        provider, source = "crossref", crossref
        data = _object(_object(_json(body, source), source).get("message"), source)
    else:
        provider, source = "datacite", datacite
        body = http.get(source)
        if body is None:
            msg = f"DOI {value!r}: no record at Crossref or DataCite"
            raise CheckError(msg)
        data = _object(_object(_object(_json(body, source), source).get("data"), source).get("attributes"), source)
    record = _record(provider, data, mapping)
    canonical = doi(_value(mapping, provider, "identifier", data))
    if canonical is None or canonical.casefold() != value.casefold():
        msg = f"{provider}: returned DOI does not match the request"
        raise CheckError(msg)
    record["identifier"] = canonical
    _require_title(record, source)
    kind = _kind(_value(mapping, provider, "resourceType", data), source)
    related: dict[str, object] = {
        term: ids
        for term in ("isVersionOf", "hasVersion")
        if (ids := [item for raw in _field(mapping, provider, term, data) if (item := doi(raw))])
    }
    if provider == "datacite" and not _is_repository(record.get("codeRepository", "")):
        # Its crosswalk also falls back to the resource landing page, which is often not a repository.
        record.pop("codeRepository", None)
    attribution = _crossref_attribution(data, mapping) if provider == "crossref" else ()
    return Work(kind, record, source, related=related, attribution=attribution)


def _crossref_attribution(data: dict[str, Any], mapping: Mapping) -> tuple[dict[str, object], ...]:
    parent = mapping.get(("crossref", "author"))
    if parent is None:
        return ()
    evidence: list[dict[str, object]] = []
    for index, author in enumerate(resolve(data, parent), 1):
        claims = author.get("role") if isinstance(author, dict) else None
        if not isinstance(claims, list):
            continue
        roles = [claim for claim in claims if isinstance(claim, dict) and claim.get("vocabulary") == "credit"]
        if roles:
            identity = person("crossref", author, parent, mapping, "author")
            evidence.append(
                {
                    "provider": "crossref",
                    "author_position": index,
                    "orcid": _checked_orcid(identity).orcid if identity else None,
                    "roles": roles,
                }
            )
    return tuple(evidence)


def _is_repository(value: str) -> bool:
    url = urlsplit(value)
    return url.scheme in {"http", "https"} and url.netloc in {"github.com", "gitlab.com", "bitbucket.org"}


def _atom_object(entry: ET.Element) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for child in entry:
        key = child.tag.rsplit("}", 1)[-1].replace("-", "_")
        if key == "author":
            data.setdefault(key, []).append(_atom_object(child))
        elif key in {"category", "link"}:
            data.setdefault(key, []).append(dict(child.attrib))
        elif child.attrib:
            data.setdefault(key, dict(child.attrib))
        elif child.text:
            data.setdefault(key, child.text.strip())
    return data


def _arxiv_work(value: str, http: Responses, mapping: Mapping) -> Work:
    source = f"https://export.arxiv.org/api/query?id_list={quote(value, safe='')}"
    body = http.required(source)
    try:
        xml = body.decode("utf-8")
        if "<!DOCTYPE" in xml or "<!ENTITY" in xml:
            msg = "arXiv: unexpected XML declaration"
            raise CheckError(msg)
        root = ET.fromstring(xml)  # noqa: S314 - bounded UTF-8 body, DTDs forbidden above
    except (ET.ParseError, UnicodeError) as err:
        msg = "arXiv: invalid Atom response"
        raise CheckError(msg) from err
    requested = _ARXIV.fullmatch(value)
    if requested is None:
        msg = "invalid arXiv identifier"
        raise CheckError(msg)
    for entry in root.findall(f"{_ATOM}entry"):
        data = _atom_object(entry)
        alternate = _value(mapping, "arxiv", "arxivId", data)
        canonical = arxiv_id(alternate) if isinstance(alternate, str) else None
        resolved = _ARXIV.fullmatch(canonical) if canonical else None
        if (
            resolved
            and resolved["id"].casefold() == requested["id"].casefold()
            and (not requested["version"] or resolved["version"] == requested["version"])
        ):
            record = _record("arxiv", data, mapping)
            record.update(arxiv=canonical, url=f"https://arxiv.org/abs/{canonical}")
            if resolved["version"]:
                record["version"] = resolved["version"]
            _require_title(record, source)
            related_doi = doi(_value(mapping, "arxiv", "relatedDoi", data))
            return Work(
                "preprint",
                record,
                source,
                revision=canonical,
                related={"journalDoi": related_doi} if related_doi else {},
            )
    msg = f"arXiv {value!r}: no matching record for the requested identifier and version"
    raise CheckError(msg)


def _repo_record(
    fmt: str, body: bytes, path: str, source: str, mapping: Mapping
) -> tuple[dict[str, Any], dict[str, Any]]:
    if fmt == "codemeta":
        data = _object(_json(body, source), source)
    else:
        try:
            data = parse_data(body.decode("utf-8"), Path(path), source)
        except UnicodeDecodeError as err:
            msg = f"{source}: citation metadata is not UTF-8"
            raise CheckError(msg) from err
    _detect_version(fmt, data, source)
    return data, _record(fmt, _adapt(fmt, data, Path(), path, mapping), mapping)


def _preferred(data: dict[str, Any], source: str, revision: str, mapping: Mapping) -> tuple[Work | None, str | None]:
    raw = _value(mapping, "cff-1.2.0", "preferredCitation", data)
    if raw is None:
        return None, None
    try:
        obj = _object(raw, source)
        kind = _kind(_value(mapping, "cff-preferred", "resourceType", obj), source)
        record = _record("cff-preferred", obj, mapping)
        _require_title(record, f"{source} preferred citation")
    except CheckError as err:
        return None, str(err)
    return Work(kind, record, source, revision), None


def _github_work(value: str, http: Responses, mapping: Mapping) -> Work:
    url = f"https://github.com/{value}"
    source = f"https://api.github.com/repos/{value}/commits?per_page=1"
    history = _json(http.required(source), source)
    first = _object(history[0], source) if isinstance(history, list) and history else {}
    revision = first.get("sha")
    if not isinstance(revision, str) or not _SHA.fullmatch(revision):
        msg = f"{url}: GitHub did not return a commit for the default branch"
        raise CheckError(msg)
    prefix = f"https://raw.githubusercontent.com/{value}/{revision}"
    for path, fmt in (("CITATION.cff", "cff-1.2.0"), ("codemeta.json", "codemeta")):
        source = f"{prefix}/{path}"
        if (body := http.get(source)) is None:
            continue
        data, record = _repo_record(fmt, body, path, source, mapping)
        raw_kind = _value(mapping, fmt, "resourceType", data)
        if fmt == "codemeta":
            if codemeta_is_dataset(data):
                raw_kind = "Dataset"
            else:
                raw_kind = _software_codemeta_type(data.get(codemeta_type_key(data)))
        kind = _kind(raw_kind or ("software" if fmt == "cff-1.2.0" else None), source)
        _require_title(record, source)
        record.setdefault("codeRepository", url)
        preferred, issue = _preferred(data, source, revision, mapping) if fmt == "cff-1.2.0" else (None, None)
        return Work(kind, record, source, revision, preferred=preferred, preferred_issue=issue)
    msg = f"{url} at {revision}: no root CITATION.cff or codemeta.json"
    raise CheckError(msg)


def _software_codemeta_type(raw: object) -> str | None:
    types = raw if isinstance(raw, list) else [raw]
    known = {
        "SoftwareSourceCode",
        "https://schema.org/SoftwareSourceCode",
        "http://schema.org/SoftwareSourceCode",
        "schema:SoftwareSourceCode",
    }
    return "SoftwareSourceCode" if any(isinstance(t, str) and t in known for t in types) else None


def resolve_work(query: Identifier, http: Responses, mapping: Mapping) -> Work:
    """Resolve the requested work and keep any alternate citation separate."""
    if query.provider == "doi":
        return _doi_work(query.value, http, mapping)
    if query.provider == "arxiv":
        return _arxiv_work(query.value, http, mapping)
    if query.provider == "openalex":
        return _openalex_identifier(query.value, http, mapping)
    return _github_work(query.value, http, mapping)


def _openalex_identifier(value: str, http: Responses, mapping: Mapping) -> Work:
    record = openalex_work(value, http.required)
    if canonical := doi(record.get("doi")):
        return _doi_work(canonical, http, mapping)
    location = record.get("primary_location")
    landing = location.get("landing_page_url") if isinstance(location, dict) else None
    if isinstance(landing, str) and (canonical := arxiv_id(landing)):
        return _arxiv_work(canonical, http, mapping)
    msg = f"OpenAlex {value}: no DOI or arXiv identifier to resolve"
    raise CheckError(msg)

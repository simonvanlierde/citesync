"""Build citations from public metadata while keeping source evidence available."""

import re
from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from citesync.cite_evidence import openalex_evidence
from citesync.cite_http import Responses
from citesync.cite_sources import Identifier, Work, arxiv_id, doi, resolve_work
from citesync.config import Config
from citesync.errors import CheckError
from citesync.export import render
from citesync.formats import Doc
from citesync.mapping import Mapping, load_mapping
from citesync.write import citation_file


def _render(work: Work, fmt: str, mapping: Mapping) -> tuple[str, list[str]]:
    if fmt not in {"cff", "codemeta"}:
        return render(fmt, work.record, kind=work.kind)
    if work.kind not in {"software", "dataset"}:
        msg = f"{fmt} is available for software and dataset citations"
        raise CheckError(msg)
    if fmt == "cff" and not work.record.get("author"):
        msg = f"{work.source}: CFF requires at least one named author"
        raise CheckError(msg)
    doc = Doc(work.source, "", work.record, frozenset(), None, release=True)
    with TemporaryDirectory() as root:
        text, skipped = citation_file(fmt, Path(root), Config(), doc, mapping, resource_type=work.kind)
    return text, [f"leaving out {term}: {reason}" for term, reason in skipped.items()]


def _check_evidence(work: Work, evidence: dict[str, object]) -> None:
    source_doi = doi(evidence.get("doi"))
    work_doi = doi(work.record.get("identifier"))
    if source_doi and work_doi and source_doi.casefold() == work_doi.casefold():
        return
    location = evidence.get("primary_location")
    landing = location.get("landing_page_url") if isinstance(location, dict) else None
    if (
        isinstance(landing, str)
        and (source_arxiv := arxiv_id(landing))
        and work.record.get("arxiv")
        and re.sub(r"v\d+$", "", source_arxiv) == re.sub(r"v\d+$", "", work.record["arxiv"])
    ):
        return
    msg = "OpenAlex work does not match the citation's DOI or arXiv ID"
    raise CheckError(msg)


def cite(
    query: Identifier,
    fmt: str,
    *,
    preferred: bool,
    openalex: str | None,
    replay: Path | None,
    save_responses: Path | None,
) -> tuple[str, list[str], dict[str, object]]:
    """Resolve and render one citation with its exact source and optional evidence."""
    package = Path(__file__).parent
    mapping_hash = sha256((package / "mapping-local.json").read_bytes()).hexdigest()
    pin = dict(
        line.split(maxsplit=1)
        for line in (package / "MAPPING_SOURCE").read_text(encoding="utf-8").splitlines()
        if line.startswith(("tag ", "commit ", "base-tag ", "status "))
    )
    http = Responses(mapping_hash, replay)
    mapping = load_mapping()
    work = resolve_work(query, http, mapping)
    selected = work
    if preferred:
        if work.preferred is None:
            msg = work.preferred_issue or f"{work.source}: no preferred citation"
            raise CheckError(msg)
        selected = work.preferred

    text, notes = _render(selected, fmt, mapping)
    evidence = openalex_evidence(openalex, http.required) if openalex else None
    if evidence is not None:
        _check_evidence(selected, evidence)
    if save_responses is not None:
        http.save(save_responses)
    result: dict[str, object] = {
        "input": asdict(query),
        "work": asdict(work),
        "selected": "preferred" if preferred else "main",
        "citation": {"format": fmt, "text": text},
        "notes": notes,
        "provenance": {**http.manifest(), "mapping": pin},
    }
    if evidence is not None:
        result["openalex"] = evidence
    return text, notes, result

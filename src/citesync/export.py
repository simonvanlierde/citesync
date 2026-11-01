"""Citations made from the source's record: BibTeX, CSL-JSON, APA 7 and schema.org JSON-LD.

A repo lists the files in the ``exports`` setting; the suffix picks the format. ``write``
keeps them in step and ``check`` reports one that isn't (``export-stale``).
"""

import datetime as dt
import json
import re
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any

from citesync.check import Finding
from citesync.config import Config
from citesync.formats import Doc, Person

# suffix: format; the longest suffix is tried first, so citation.csl.json is never plain JSON
SUFFIXES = {".csl.json": "csl-json", ".apa.txt": "apa", ".bib": "bibtex", ".jsonld": "jsonld"}
FORMATS = tuple(SUFFIXES.values())
# The file each format goes to when no path is given: the playground's names.
DEFAULT_NAMES = {fmt: f"citation{suffix}" for suffix, fmt in SUFFIXES.items()} | {"jsonld": "schema.jsonld"}

_TEX = {
    "\\": r"\textbackslash{}",
    "{": r"\{",
    "}": r"\}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
# Latin letters NFKD leaves whole, so they would drop out of an ASCII key
_LATIN = str.maketrans(
    {"ł": "l", "ø": "o", "đ": "d", "ħ": "h", "\u0131": "i", "ß": "ss", "æ": "ae", "œ": "oe", "þ": "th"}
)
_SPDX_ID = re.compile(r"[A-Za-z0-9.+-]+")


def format_of(path: str) -> str | None:
    """The export format a path's suffix names, or None."""
    name = PurePosixPath(path).name
    return next((fmt for suffix, fmt in SUFFIXES.items() if name.endswith(suffix) and name != suffix), None)


def text(path: str, rec: dict[str, Any]) -> str:
    """The text the export at ``path`` should hold; config has checked its suffix."""
    fmt = format_of(path)
    if fmt is None:
        msg = f"{path}: not an export suffix"
        raise ValueError(msg)
    return render(fmt, rec)[0]


def record(docs: list[Doc]) -> dict[str, Any]:
    """Each term from the first readable doc that holds it, the source first: what the exports cite."""
    merged: dict[str, Any] = {}
    for doc in docs:
        if doc.readable:
            for term, value in doc.record.items():
                merged.setdefault(term, value)
    return merged


def render(fmt: str, rec: dict[str, Any]) -> tuple[str, list[str]]:
    """The export's text in ``fmt``, and notes on what it left out. Never invents a release date."""
    day, notes = None, []
    if date := rec.get("datePublished"):
        try:
            day = dt.date.fromisoformat(date)
        except ValueError:
            if fmt != "jsonld":  # JSON-LD carries the date as written
                notes.append("BibTeX, CSL-JSON and APA: release date omitted because it is not a full YYYY-MM-DD date.")
    return _WRITERS[fmt](rec, day), notes


def citations(rec: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Every format under its default name, and the notes once each."""
    files, notes = {}, []
    for fmt, name in DEFAULT_NAMES.items():
        files[name], left = render(fmt, rec)
        notes += left
    return files, list(dict.fromkeys(notes))


def tex(text: str) -> str:
    """Escape a literal UTF-8 metadata value for a braced BibTeX field."""
    return "".join(_TEX.get(char, char) for char in " ".join(text.split()))


def key(rec: dict[str, Any]) -> str:
    """The citation key: the title up to any subtitle, in lowercase ASCII with dashes (``credit-matrix``)."""
    title = re.split(":|\\s[-\u2013\u2014]\\s", rec.get("name", ""), maxsplit=1)[0]
    ascii_ = unicodedata.normalize("NFKD", title.lower().translate(_LATIN)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-") or "software"


def stale(root: Path, docs: list[Doc], config: Config) -> list[Finding]:
    """An ``export-stale`` finding for each listed export that is missing or differs from what the source gives."""
    if not config.exports or not docs[0].readable:
        return []
    rec, found = record(docs), []
    for path in config.exports:
        file = root / path
        if not file.is_file():
            found.append(Finding(path, None, "export-stale", "missing"))
        elif file.read_bytes().decode("utf-8", "replace").replace("\r\n", "\n") != text(path, rec):
            found.append(Finding(path, None, "export-stale", "differs from what the source gives"))
    return found


def _bibtex(rec: dict[str, Any], day: dt.date | None) -> str:
    authors = []
    for p in _people(rec):
        if p.organization or not p.family:
            authors.append("{" + tex(p.name or "") + "}")
        else:
            authors.append("{" + tex(p.family) + "}" + (", {" + tex(p.given) + "}" if p.given else ""))
    fields = {"title": "{" + tex(rec["name"]) + "}", "author": " and ".join(authors)}
    for term, field in (("identifier", "doi"), ("codeRepository", "url")):
        if value := rec.get(term):
            fields[field] = tex(value)
    fields["note"] = tex("Software" + (f", version {rec['version']}" if rec.get("version") else ""))
    if day:
        fields["year"] = str(day.year)
    return f"@misc{{{key(rec)},\n" + "".join(f"  {k} = {{{v}}},\n" for k, v in fields.items()) + "}\n"


def _csl(rec: dict[str, Any], day: dt.date | None) -> str:
    authors = []
    for p in _people(rec):
        if p.organization or not p.family:
            authors.append({"literal": p.name})
        else:
            authors.append({"family": p.family} | ({"given": p.given} if p.given else {}))
    csl: dict[str, Any] = {"id": key(rec), "type": "software", "title": rec["name"], "author": authors}
    for term, field in (("identifier", "DOI"), ("codeRepository", "URL"), ("version", "version")):
        if value := rec.get(term):
            csl[field] = value
    if day:
        csl["issued"] = {"date-parts": [[day.year, day.month, day.day]]}
    return json.dumps([csl], indent=2, ensure_ascii=False) + "\n"


def _apa(rec: dict[str, Any], day: dt.date | None) -> str:
    """An APA 7 software reference: ``Family, G. (2026). Title (Version 1.0) [Computer software]. URL``."""
    names = [_apa_name(p) for p in _people(rec)]
    if len(names) > 20:  # APA 7: the first 19, an ellipsis, then the last
        authors = ", ".join(names[:19]) + ", . . . " + names[-1]
    elif len(names) > 1:
        authors = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        authors = "".join(names)
    work = f"{rec['name']}" + (f" (Version {rec['version']})" if rec.get("version") else "") + " [Computer software]."
    year = f"({day.year if day else 'n.d.'})."
    # APA 7: with no author, the title takes the author's place
    text = f"{authors}{'' if authors.endswith('.') else '.'} {year} {work}" if authors else f"{work} {year}"
    doi = rec.get("identifier")
    link = f"https://doi.org/{doi}" if doi else rec.get("codeRepository")
    return f"{text} {link}\n" if link else f"{text}\n"


def _apa_name(p: Person) -> str:
    if p.organization or not p.family:
        return p.name or ""
    initials = _initials(p.given)
    return f"{p.family}, {initials}" if initials else p.family


def _jsonld(rec: dict[str, Any], _day: dt.date | None) -> str:
    """schema.org ``SoftwareSourceCode`` with the plain schema.org context, which search engines read."""
    data: dict[str, Any] = {"@context": "https://schema.org", "@type": "SoftwareSourceCode", "name": rec["name"]}
    for term in ("description", "version", "codeRepository", "datePublished"):
        if value := rec.get(term):
            data[term] = value
    if doi := rec.get("identifier"):
        data["identifier"] = f"https://doi.org/{doi}"
    if licence := rec.get("license"):
        data["license"] = f"https://spdx.org/licenses/{licence}" if _SPDX_ID.fullmatch(licence) else licence
    if keywords := rec.get("keywords"):
        data["keywords"] = list(keywords)
    for term in ("author", "contributor"):
        if people := [_schema_person(p) for p in rec.get(term, ()) if p.name]:
            data[term] = people
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _schema_person(p: Person) -> dict[str, str]:
    if p.organization:
        return {"@type": "Organization", "name": p.name or ""}
    node = {"@type": "Person"} | ({"@id": f"https://orcid.org/{p.orcid}"} if p.orcid else {})
    for field, value in (("givenName", p.given), ("familyName", p.family), ("name", p.name)):
        if value:
            node[field] = value
    return node


def _people(rec: dict[str, Any]) -> list[Person]:
    return [p for p in rec.get("author", ()) if p.name]


def _initials(given: str | None) -> str:
    """``Marie`` as ``M.``, ``Jean-Paul`` as ``J.-P.``, ``Tu Youyou``'s ``Youyou`` as ``Y.``."""
    return " ".join("-".join(f"{part[0]}." for part in word.split("-") if part) for word in (given or "").split())


_WRITERS = {"bibtex": _bibtex, "csl-json": _csl, "apa": _apa, "jsonld": _jsonld}
_LABELS = {"bibtex": "BibTeX", "csl-json": "CSL-JSON", "apa": "APA", "jsonld": "JSON-LD"}

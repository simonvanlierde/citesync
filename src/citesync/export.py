"""Citations made from the source's record: BibTeX, CSL-JSON, APA 7, JSON-LD and DataCite XML.

A repo lists the files in the ``exports`` setting; the suffix picks the format. ``write``
keeps them in step and ``check`` reports one that isn't (``export-stale``).
"""

import datetime as dt
import json
import re
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path, PurePosixPath
from typing import Any

from citesync.check import Finding
from citesync.config import Config
from citesync.errors import CheckError
from citesync.formats import Doc, Person
from citesync.mapping import _parse, load_mapping, person_terms, relative

# suffix: format; the longest suffix is tried first, so citation.csl.json is never plain JSON
SUFFIXES = {
    ".csl.json": "csl-json",
    ".apa.txt": "apa",
    ".bib": "bibtex",
    ".jsonld": "jsonld",
    ".datacite.xml": "datacite",
}
# The file each format goes to when no path is given: the playground's names.
DEFAULT_NAMES = {
    "csl-json": "citation.csl.json",
    "apa": "citation.apa.txt",
    "bibtex": "citation.bib",
    "jsonld": "schema.jsonld",
    "datacite": "citation.datacite.xml",
}

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
_SPDX_ID = re.compile(r"(?!LicenseRef-)[A-Za-z0-9.+-]+")  # one licence id; an expression or LicenseRef has no page
_URL = re.compile(r"https?://\S+")
_SPDX_PAGES = "https://spdx.org/licenses/"


def format_of(path: str) -> str | None:
    """The export format a path's suffix names, or None."""
    name = PurePosixPath(path).name
    return next((fmt for suffix, fmt in SUFFIXES.items() if name.endswith(suffix) and name != suffix), None)


def text(path: str, rec: dict[str, Any]) -> str:
    """The text the export at ``path`` should hold; config has checked its suffix."""
    return render(str(format_of(path)), rec)[0]


def record(docs: list[Doc]) -> dict[str, Any]:
    """Each term from the first doc that holds it, the source first: what the exports cite.

    An unreadable doc has an empty record, so it gives nothing.
    """
    merged: dict[str, Any] = {}
    for doc in docs:
        for term, value in doc.record.items():
            merged.setdefault(term, value)
    return merged


def render(fmt: str, rec: dict[str, Any]) -> tuple[str, list[str]]:
    """The export's text in ``fmt``, and notes on what it left out. Never invents a release date.

    Raises:
        CheckError: when the record has no title.
    """
    if not rec.get("name"):
        msg = "no file gives a title, which a citation needs"
        raise CheckError(msg)
    day, notes = _date(rec.get("datePublished")), []
    if rec.get("datePublished") and day is None and fmt != "jsonld":  # JSON-LD carries the date as written
        notes.append(
            "BibTeX, CSL-JSON and APA: release date omitted because it is not a YYYY, YYYY-MM or YYYY-MM-DD date."
        )
    return _WRITERS[fmt](rec, day), notes


def _date(value: str | None) -> tuple[int, ...] | None:
    """``2026-10-31`` as ``(2026, 10, 31)``, ``2026`` as ``(2026,)``; None for anything else."""
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?", value or "")
    if not match:
        return None
    parts = tuple(int(p) for p in match.groups() if p)
    try:
        dt.date(*parts, *(1,) * (3 - len(parts)))
    except ValueError:
        return None
    return parts


def citations(rec: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Every format under its default name, and the notes once each."""
    files, notes = {}, []
    for fmt, name in DEFAULT_NAMES.items():
        try:
            files[name], left = render(fmt, rec)
        except CheckError:
            if fmt != "datacite":  # the others need only a title; DataCite also needs a DOI and a publisher
                raise
            continue
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


def refusal(path: str, rec: dict[str, Any]) -> str | None:
    """Why the export at ``path`` can't be made from ``rec``, or None when it can."""
    try:
        text(path, rec)
    except CheckError as err:
        return str(err)
    return None


def stale(root: Path, docs: list[Doc], config: Config) -> list[Finding]:
    """An ``export-stale`` finding for each listed export that is missing or differs from what the source gives."""
    if not config.exports or not docs[0].readable:
        return []
    rec, found = record(docs), []
    if not rec.get("name"):
        return [Finding(path, None, "export-stale", "can't be made: no file gives a title") for path in config.exports]
    for path in config.exports:
        file = root / path
        if not writable(root, path):
            found.append(Finding(path, None, "export-stale", "can't be written: a link, a folder, or under a file"))
        elif reason := refusal(path, rec):
            found.append(Finding(path, None, "export-stale", f"can't be made: {reason}"))
        elif not file.is_file():
            found.append(Finding(path, None, "export-stale", "missing"))
        elif file.read_bytes().decode("utf-8", "replace").replace("\r\n", "\n") != text(path, rec):
            found.append(Finding(path, None, "export-stale", "differs from what the source gives"))
    return found


def writable(root: Path, path: str) -> bool:
    """Whether ``write`` may make the export: no link on the way, folders above it, and a file or nothing there.

    An export is written whole, so a link could replace the file it points at, CITATION.cff included.
    """
    parts = PurePosixPath(path).parts
    for i in range(1, len(parts) + 1):
        here = root.joinpath(*parts[:i])
        if here.is_symlink() or (i < len(parts) and here.exists() and not here.is_dir()):
            return False
    return not (root / path).exists() or (root / path).is_file()


def _bibtex(rec: dict[str, Any], day: tuple[int, ...] | None) -> str:
    """A biblatex-software ``@software`` entry, each field named as codemeta-drift's bibtex rows name it.

    A row with alternatives (``date | year``) writes each one, so plain BibTeX styles, which print an
    unknown type as ``@misc``, still find the field they read.
    """
    rows = load_mapping()
    authors = []
    for p in _people(rec):
        if p.organization or not p.family:
            authors.append("{" + tex(p.name or "") + "}")
        else:
            authors.append("{" + tex(p.family) + "}" + (", {" + tex(p.given) + "}" if p.given else ""))
    values = {
        "name": "{" + tex(rec["name"]) + "}",
        "author": " and ".join(authors),
        "version": tex(rec.get("version") or ""),
        "datePublished": "-".join(f"{part:02d}" for part in day) if day else "",
        "identifier": str(rec.get("identifier") or ""),
        "swhid": str(rec.get("swhid") or ""),
        "codeRepository": str(rec.get("codeRepository") or ""),
        "license": tex(rec.get("license") or ""),
        "description": tex(rec.get("description") or ""),
        "keywords": tex(", ".join(rec.get("keywords") or ())),
    }
    verbatim = {"identifier", "swhid", "codeRepository"}  # biblatex reads these as written: only braces would break
    fields: dict[str, str] = {}
    for term, value in values.items():
        names = str(rows["bibtex", term] or "").split(" | ")
        for name in names if value else ():
            text = value.replace("{", "%7B").replace("}", "%7D") if term in verbatim else value
            fields.setdefault(name, str(day[0]) if name == "year" and day else text)
    return f"@software{{{key(rec)},\n" + "".join(f"  {k} = {{{v}}},\n" for k, v in fields.items()) + "}\n"


def _csl(rec: dict[str, Any], day: tuple[int, ...] | None) -> str:
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
        csl["issued"] = {"date-parts": [list(day)]}
    return json.dumps([csl], indent=2, ensure_ascii=False) + "\n"


def _apa(rec: dict[str, Any], day: tuple[int, ...] | None) -> str:
    """An APA 7 software reference: ``Family, G. (2026). Title (Version 1.0) [Computer software]. URL``."""
    names = [_apa_name(p) for p in _people(rec)]
    if len(names) > 20:  # APA 7: the first 19, an ellipsis, then the last
        authors = ", ".join(names[:19]) + ", . . . " + names[-1]
    elif len(names) > 1:
        authors = ", ".join(names[:-1]) + ", & " + names[-1]
    else:
        authors = "".join(names)
    work = f"{rec['name']}" + (f" (Version {rec['version']})" if rec.get("version") else "") + " [Computer software]."
    year = f"({day[0] if day else 'n.d.'})."
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


def _jsonld(rec: dict[str, Any], _day: tuple[int, ...] | None) -> str:
    """schema.org ``SoftwareSourceCode`` with the plain schema.org context, which search engines read."""
    data: dict[str, Any] = {"@context": "https://schema.org", "@type": "SoftwareSourceCode", "name": rec["name"]}
    for term in ("description", "version", "codeRepository", "datePublished"):
        if value := rec.get(term):
            data[term] = value
    if doi := rec.get("identifier"):
        data["identifier"] = f"https://doi.org/{doi}"
    if licence := rec.get("license"):
        if _SPDX_ID.fullmatch(licence):
            data["license"] = f"https://spdx.org/licenses/{licence}"
        elif _URL.fullmatch(licence):
            data["license"] = licence  # schema.org takes a URL here; an expression or LicenseRef has none
    if keywords := rec.get("keywords"):
        data["keywords"] = list(keywords)
    for term in ("author", "contributor"):
        if people := [_schema_person(p) for p in rec.get(term, ()) if p.name]:
            data[term] = people
    # a site embeds this in a <script> tag, where a literal </script> in a title would end it
    return json.dumps(data, indent=2, ensure_ascii=False).replace("<", "\\u003c") + "\n"


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
    return " ".join(
        "-".join(f"{part[0].upper()}." for part in word.split("-") if part) for word in (given or "").split()
    )


# DataCite Metadata Schema 4.7. Its top-level elements must come in this order (the xs:sequence).
_DATACITE_ORDER = (
    "identifier", "creators", "titles", "publisher", "publicationYear", "resourceType", "subjects",
    "contributors", "dates", "relatedIdentifiers", "version", "rightsList", "descriptions",
)  # fmt: skip
_DATACITE_NS = "http://datacite.org/schema/kernel-4"
_DATACITE_XSD = "http://schema.datacite.org/meta/kernel-4.7/metadata.xsd"
# Where a DataCite JSON key and its XML element or attribute differ. The rows are the REST JSON paths.
_XML_NAMES = {"doi": "identifier", "types": "resourceType", "rightsUri": "rightsURI"}
_XML_ATTRIBUTES = {"rightsUri", "resourceTypeGeneral"}  # JSON keys that are XML attributes
_XML_FIXED = {"doi": {"identifierType": "DOI"}}  # attributes the XML needs and the JSON key implies
_XML_BAD = re.compile("[^\t\n\r -\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]")  # not allowed in XML 1.0


def datacite_slots(path: str) -> list[tuple[list[str], dict[str, str], str | None]]:
    """Where the DataCite XML holds the value of a row's JSON path: one slot per alternative.

    A slot is the element names from the root down, the attributes that element needs, and the
    attribute that holds the value (None when the element's text does). The rule, step by step:

    - ``key[]`` at the top is a wrapper and its singular item: ``titles[]`` is ``<titles><title>``;
      deeper, it is only the item (``nameIdentifiers[]`` is ``<nameIdentifier>``). The singular drops
      ``List`` or a trailing ``s``.
    - a step that repeats the item's name (``titles[].title``) is the item itself.
    - ``[k=v]`` is the attribute ``k="v"`` on the item.
    - ``publisher.name`` is the text of ``publisher``: the JSON nests a name that the XML holds as text.
    - the few names in ``_XML_NAMES`` differ between JSON and XML.
    """
    slots = []
    for (steps,) in _parse(path):
        if len(steps) > 1 and steps[-1][0] == "name" and not steps[-2][3]:
            steps = steps[:-1]  # noqa: PLW2901
        names, attrs, leaf, item = [], {}, None, ""
        for i, (key, fkey, fvalue, is_list) in enumerate(steps):
            attrs |= _XML_FIXED.get(key, {})
            xml = _XML_NAMES.get(key, key)
            if key in _XML_ATTRIBUTES:
                leaf = xml
            elif xml != item:
                item = ""
                if is_list:
                    item = xml.removesuffix("List") if xml.endswith("List") else xml.removesuffix("s")
                    names += [xml, item] if i == 0 else [item]
                else:
                    names.append(xml)
            if fkey:
                attrs[fkey] = str(fvalue)
        if (names, attrs, leaf) not in slots:  # ``publisher.name | publisher`` is one element
            slots.append((names, attrs, leaf))
    return slots


def _datacite(rec: dict[str, Any], day: tuple[int, ...] | None) -> str:  # noqa: C901 - one branch per property
    """DataCite 4.7 XML, each element placed where codemeta-drift's datacite rows say (``datacite_slots``).

    Raises:
        CheckError: when the record lacks a property the schema requires: DOI, author, publisher or release year.
    """
    _datacite_require(rec, day)
    rows = load_mapping()
    root = ET.Element(
        "resource",
        {
            "xmlns": _DATACITE_NS,
            "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            "xsi:schemaLocation": f"{_DATACITE_NS} {_DATACITE_XSD}",
        },
    )

    def put(term: str, value: str | None, extra: dict[str, str] | None = None, text: str | None = None) -> None:
        for names, attrs, leaf in datacite_slots(str(rows["datacite", term])):
            if names[0] not in _DATACITE_ORDER:
                continue  # an alternative for the REST JSON that the XML has no element for, such as ``url``
            node = _wrappers(root, names[:-1])
            year = names[-1] == "publicationYear"
            shown = _xml(f"{day[0]:04d}" if year and day else value or "")
            el = ET.SubElement(node, names[-1], attrs | (extra or {}))
            if leaf and value is not None:
                el.set(leaf, shown)
            if text is not None:
                el.text = _xml(text)
            elif not leaf or leaf == "resourceTypeGeneral":
                el.text = shown

    put("identifier", rec["identifier"])
    for term, role in (("author", "creator"), ("contributor", "contributor")):
        row = str(rows["datacite", term])
        names = datacite_slots(row)[0][0]
        for p in (p for p in rec.get(term, ()) if p.name and _xml(p.name)):
            node = ET.SubElement(_wrappers(root, names[:-1]), names[-1])
            if term == "contributor":
                node.set("contributorType", "Other")  # required; the source holds no role
            _datacite_person(node, p, term, role)
    put("name", rec["name"])
    put("publisher", rec["publisher"])
    put("datePublished", "-".join(f"{part:02d}" if i else f"{part:04d}" for i, part in enumerate(day or ())))
    put("resourceType", "Software")
    for keyword in dict.fromkeys(filter(None, map(_xml, rec.get("keywords", ())))):
        put("keywords", keyword)
    for term in ("version", "description"):
        if _xml(rec.get(term) or ""):
            put(term, rec[term])
    if licence := _xml(rec.get("license") or ""):
        if _SPDX_ID.fullmatch(licence):  # SPDX attribute names are the schema's; no row names them
            spdx = {"rightsIdentifier": licence, "rightsIdentifierScheme": "SPDX", "schemeURI": _SPDX_PAGES}
            put("license", f"{_SPDX_PAGES}{licence}.html", spdx)
        elif _URL.fullmatch(licence):
            put("license", licence)
        else:
            put("license", None, text=licence)  # an expression or LicenseRef has no URI: the text is the licence
    if _xml(rec.get("codeRepository") or ""):
        put("codeRepository", rec["codeRepository"], {"relatedIdentifierType": "URL"})
    root[:] = sorted(root, key=lambda el: _DATACITE_ORDER.index(el.tag))
    ET.indent(root)
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode") + "\n"


def _datacite_require(rec: dict[str, Any], day: tuple[int, ...] | None) -> None:
    for value, why in (  # checked after cleaning, so a value of only control characters counts as missing
        (_xml(rec["name"]), "no file gives a title"),
        (
            _xml(rec.get("identifier") or ""),
            "no file gives a DOI: set `doi` in CITATION.cff or `identifier` in codemeta.json",
        ),
        ([p for p in _people(rec) if _xml(p.name or "")], "no file gives an author"),
        (_xml(str(rec.get("publisher") or "")), "no file gives a publisher: set `publisher` in codemeta.json"),
        (day, "no release year: set `date-released` in CITATION.cff or `datePublished` in codemeta.json"),
    ):
        if not value:
            msg = f"{why}, which DataCite requires"
            raise CheckError(msg)


def _wrappers(root: ET.Element, names: list[str]) -> ET.Element:
    """The element under ``root`` named by ``names`` (``creators``), made when it isn't there yet."""
    node = root
    for name in names:
        found = node.find(name)
        node = found if found is not None else ET.SubElement(node, name)
    return node


def _datacite_person(node: ET.Element, p: Person, term: str, role: str) -> None:
    """A creator or contributor: the name, and for a person the given and family names and the ORCID.

    NOTE: ``creatorName`` and ``contributorName`` are required children of the element the
    ``author`` and ``contributor`` rows name, and no row names them; the schema fixes them.
    """
    rows = load_mapping()
    given_row, family_row, orcid_row = (str(rows["datacite", t]) for t in person_terms(term))
    row = str(rows["datacite", term])
    personal = not p.organization
    name = ET.SubElement(node, f"{role}Name", {"nameType": "Personal" if personal else "Organizational"})
    # DataCite writes a personal name "Family, Given" when both parts are known, else as given
    name.text = _xml(f"{p.family}, {p.given}" if personal and p.family and p.given else p.name or "")
    if personal:
        for sub, value in ((given_row, p.given), (family_row, p.family)):
            if value and _xml(value):
                ET.SubElement(node, datacite_slots(relative(sub, row))[0][0][-1]).text = _xml(value)
    if p.orcid:
        names, attrs, _ = datacite_slots(relative(orcid_row, row))[0]
        ET.SubElement(node, names[-1], attrs).text = f"https://orcid.org/{p.orcid}"


def _xml(value: str) -> str:
    """``value`` as XML 1.0 text: no forbidden characters, whitespace runs (CR included) as one space.

    One space keeps a file that a checkout turned to CRLF equal to what is exported.
    """
    return " ".join(_XML_BAD.sub("", value).split())


_WRITERS = {"bibtex": _bibtex, "csl-json": _csl, "apa": _apa, "jsonld": _jsonld, "datacite": _datacite}

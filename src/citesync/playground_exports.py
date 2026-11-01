"""Citation exports and explicitly incomplete package metadata templates for the playground."""

import datetime as dt
import json
import re
from typing import Any

import tomlkit
from packaging.utils import InvalidName, canonicalize_name

from citesync import codecs
from citesync.errors import CannotWrite
from citesync.formats import Person

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
_CARGO_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_NPM_NAME = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")


def tex(text: str) -> str:
    """Escape a literal UTF-8 metadata value for a braced BibTeX field."""
    return "".join(_TEX.get(char, char) for char in " ".join(text.split()))


def bibliography(record: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Write BibTeX misc and CSL software citations; never invent a release date."""
    people: tuple[Person, ...] = record.get("author", ())
    csl: dict[str, Any] = {"id": "software", "type": "software", "title": record["name"], "author": []}
    csl["author"], authors = _citation_people(people)
    fields = {"title": "{" + tex(record["name"]) + "}", "author": " and ".join(authors)}
    for term, key in (("identifier", "DOI"), ("codeRepository", "URL"), ("version", "version")):
        if value := record.get(term):
            csl[key] = value
    for term, key in (("identifier", "doi"), ("codeRepository", "url")):
        if value := record.get(term):
            fields[key] = tex(value)
    fields["note"] = tex("Software" + (f", version {record['version']}" if record.get("version") else ""))
    notes = []
    if date := record.get("datePublished"):
        try:
            day = dt.date.fromisoformat(date)
        except ValueError:
            notes.append("BibTeX and CSL-JSON: release date omitted because it is not a full YYYY-MM-DD date.")
        else:
            csl["issued"] = {"date-parts": [[day.year, day.month, day.day]]}
            fields["year"] = str(day.year)
    bib = "@misc{software,\n" + "".join(f"  {key} = {{{value}}},\n" for key, value in fields.items()) + "}\n"
    return {"citation.bib": bib, "citation.csl.json": json.dumps([csl], indent=2, ensure_ascii=False) + "\n"}, notes


def _citation_people(people: tuple[Person, ...]) -> tuple[list[dict[str, str]], list[str]]:
    names, authors = [], []
    for person in people:
        if not person.name:
            continue
        if person.organization or not person.family:
            names.append({"literal": person.name})
            authors.append("{" + tex(person.name) + "}")
        else:
            name = {"family": person.family}
            author = "{" + tex(person.family) + "}"
            if person.given:
                name["given"] = person.given
                author += ", {" + tex(person.given) + "}"
            names.append(name)
            authors.append(author)
    return names, authors


def package_templates(record: dict[str, Any]) -> tuple[dict[str, str], list[str]]:
    """Write metadata-only manifests; omitted naming/version values need explicit review."""
    templates, notes = {}, []
    people = [person.name for person in record.get("author", ()) if person.name]
    for filename in ("pyproject.toml", "Cargo.toml", "package.json"):
        data, omitted = _package_metadata(record, filename)
        notes.extend(omitted)
        if filename == "pyproject.toml":
            data["authors"] = [{"name": name} for name in people]
            if repository := record.get("codeRepository"):
                data["urls"] = {"Repository": repository}
            text = tomlkit.dumps({"project": data})
        else:
            if record.get("codeRepository"):
                data["repository"] = record["codeRepository"]
            if filename == "Cargo.toml":
                data["authors"] = people
                text = tomlkit.dumps({"package": data})
            else:
                data["private"] = True
                if people:
                    data["author"] = {"name": people[0]}
                if len(people) > 1:
                    notes.append("package.json: only the first author is carried over; npm has one author slot.")
                templates[filename] = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
                continue
        templates[filename] = (
            "# Incomplete metadata template: review build settings, sources and dependencies.\n" + text
        )
    return templates, notes


def _package_metadata(record: dict[str, Any], filename: str) -> tuple[dict[str, Any], list[str]]:
    data: dict[str, Any] = {}
    notes = []
    name = record["name"]
    if _package_name(name, filename):
        data["name"] = name
    else:
        notes.append(f"{filename}: name omitted; choose an identifier that meets the package naming rules.")
    for term in ("description", "license"):
        if record.get(term):
            data[term] = record[term]
    if version := record.get("version"):
        try:
            data["version"] = _manifest_version(version, filename)
        except CannotWrite as error:
            notes.append(f"{filename}: version omitted: {error}")
    else:
        notes.append(f"{filename}: add a release version before using this template.")
    return data, notes


def _package_name(name: str, filename: str) -> bool:
    if filename == "pyproject.toml":
        try:
            canonicalize_name(name, validate=True)
        except InvalidName:
            return False
        return True
    if filename == "Cargo.toml":
        return _CARGO_NAME.fullmatch(name) is not None
    return len(name) <= 214 and _NPM_NAME.fullmatch(name) is not None


def _manifest_version(version: str, filename: str) -> str:
    if filename != "pyproject.toml":
        return codecs.version_encode_semver(version)
    key = codecs.version_key(version)
    if isinstance(key, str):
        msg = f"{version} is not a PEP 440 version"
        raise CannotWrite(msg)
    return str(key)

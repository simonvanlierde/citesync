"""Explicitly incomplete package metadata templates for the playground."""

import io
import json
import re
from typing import Any

import tomlkit
from packaging.utils import InvalidName, canonicalize_name
from ruamel.yaml import YAML

from citesync import codecs
from citesync.errors import CannotWrite
from citesync.mapping import load_mapping
from citesync.research_metadata import R_PACKAGE

_CARGO_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*")
_NPM_NAME = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")
_R_VERSION = re.compile(r"\d+(?:[.-]\d+)+")
_JULIA_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_TYPST_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_TYPST_VERSION = re.compile(r"\d+\.\d+\.\d+")
_R_GPL = re.compile(r"(A?L?GPL)-(\d)(?:\.0|(\.\d))-(only|or-later)")


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
    templates["DESCRIPTION"] = _description(record, notes)
    templates["Project.toml"] = _julia_project(record, notes)
    templates["typst.toml"] = _typst_manifest(record, notes)
    templates["_extension.yml"] = _quarto_manifest(record, notes)
    return templates, notes


def _plugin_fields(record: dict[str, Any], notes: list[str], fmt: str, filename: str) -> tuple[dict[str, Any], Any]:
    """The name and version of a plugin manifest, and ``put(term, value)``, which writes at the row's path."""
    rows = load_mapping()
    data: dict[str, Any] = {}

    def put(term: str, value: object) -> None:
        if path := rows[(fmt, term)]:  # a term the format has no place for is dropped
            *parents, key = path.removesuffix("[]").split(".")
            node = data
            for parent in parents:
                node = node.setdefault(parent, {})
            node[key] = value

    if fmt == "quarto" or _TYPST_NAME.fullmatch(record["name"]):
        put("name", record["name"])
    else:
        notes.append(f"{filename}: name omitted; use lower-case letters, numbers and hyphens, such as lensgrind.")
    if version := record.get("version"):
        try:
            semver = codecs.version_encode_semver(version)
            if fmt == "typst" and not _TYPST_VERSION.fullmatch(semver):
                msg = f"Typst package versions are major.minor.patch only, not {semver}"  # as write's typst.toml rule
                raise CannotWrite(msg)  # noqa: TRY301
            put("version", semver)
        except CannotWrite as error:
            notes.append(f"{filename}: version omitted: {error}")
    else:
        notes.append(f"{filename}: add a release version before using this template.")
    return data, put


def _typst_manifest(record: dict[str, Any], notes: list[str]) -> str:
    """A Typst typst.toml, each field at the path of codemeta-drift's typst row."""
    data, put = _plugin_fields(record, notes, "typst", "typst.toml")
    put("author", [person.name for person in record.get("author", ()) if person.name])
    for term in ("license", "description", "codeRepository"):
        if record.get(term):
            put(term, record[term])
    if record.get("keywords"):
        put("keywords", list(record["keywords"]))
    notes.append("typst.toml: add the entrypoint and compiler version, and a handle or email to each author.")
    return "# Incomplete metadata template: review entrypoint, compiler and exclude.\n" + tomlkit.dumps(data)


def _quarto_manifest(record: dict[str, Any], notes: list[str]) -> str:
    """A Quarto _extension.yml, each field at the path of codemeta-drift's quarto row."""
    data, put = _plugin_fields(record, notes, "quarto", "_extension.yml")
    names = [person.name for person in record.get("author", ()) if person.name]
    if names:
        put("author", names[0])
    if len(names) > 1:
        notes.append("_extension.yml: only the first author is carried over; Quarto has one author string.")
    notes.append("_extension.yml: add quarto-required and contributes under _extensions/<name>/.")
    buffer = io.StringIO()
    YAML().dump(data, buffer)
    return "# Incomplete metadata template: review quarto-required and contributes.\n" + buffer.getvalue()


def _description(record: dict[str, Any], notes: list[str]) -> str:
    """An R DESCRIPTION, each field where codemeta-drift's r-description rows read it."""
    package, _, title = record["name"].partition(": ")  # the R import names a package `Package: Title`
    fields = {}
    if R_PACKAGE.fullmatch(package):
        fields["Package"] = package
    else:
        notes.append("DESCRIPTION: Package omitted; use letters, numbers and dots, starting with a letter.")
    if title:
        fields["Title"] = title
    else:
        notes.append("DESCRIPTION: add a Title, a one-line summary in title case.")
    if (version := record.get("version")) and _R_VERSION.fullmatch(version):
        fields["Version"] = version
    else:
        notes.append("DESCRIPTION: Version omitted; R needs two or more numbers, such as 1.4.0.")
    people = [_r_person(p, "aut") for p in record.get("author", ()) if p.name]  # an ORCID alone names no one
    people += [_r_person(p, "ctb") for p in record.get("contributor", ()) if p.name]
    if people:
        fields["Authors@R"] = "c(\n" + ",\n".join(f"    {p}" for p in people) + "\n  )"
    notes.append("DESCRIPTION: give the maintainer the role cre and an email, as CRAN asks.")
    if description := record.get("description"):
        fields["Description"] = " ".join(description.split())
    if licence := record.get("license"):
        fields["License"] = _R_GPL.sub(_r_gpl, licence).replace(" OR ", " | ")  # R separates choices with |
        notes.append("DESCRIPTION: check License against R's licence names; MIT and BSD add + file LICENSE.")
    if repository := record.get("codeRepository"):
        fields["URL"] = repository
    fields["Encoding"] = "UTF-8"
    return "".join(f"{key}: {value}\n" for key, value in fields.items())


def _r_gpl(match: re.Match[str]) -> str:
    version = match[2] + (match[3] or "")  # R drops a .0: GPL-3, but LGPL-2.1
    return f"{match[1]}-{version}" if match[4] == "only" else f"{match[1]} (>= {version})"


def _r_person(person: Any, role: str) -> str:  # noqa: ANN401 - a citesync.formats.Person
    if person.given and person.family:
        parts = [_r_string(person.given), _r_string(person.family)]
    elif person.family and not person.organization:
        parts = [f"family = {_r_string(person.family)}"]
    else:
        parts = [_r_string(person.name)]
    parts.append(f'role = "{role}"')
    if person.orcid:
        parts.append(f"comment = c(ORCID = {_r_string(person.orcid)})")
    return f"person({', '.join(parts)})"


def _r_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _julia_project(record: dict[str, Any], notes: list[str]) -> str:
    """A Julia Project.toml, with authors as CFF tables as codemeta-drift's julia rows read them."""
    data: dict[str, Any] = {}
    if _JULIA_NAME.fullmatch(record["name"]):
        data["name"] = record["name"]
    else:
        notes.append("Project.toml: name omitted; a Julia package name is an identifier, such as Lensgrind.")
    notes.append("Project.toml: add the uuid Pkg generates for a new package.")
    if version := record.get("version"):
        try:
            data["version"] = codecs.version_encode_semver(version)
        except CannotWrite as error:
            notes.append(f"Project.toml: version omitted: {error}")
    authors = []
    for person in record.get("author", ()):
        if not person.name:  # an ORCID alone names no one
            continue
        if person.given and person.family:
            author = {"given-names": person.given, "family-names": person.family}
        elif person.family and not person.organization:
            author = {"family-names": person.family}
        else:
            author = {"name": person.name}
        if person.orcid:
            author["orcid"] = codecs.orcid_encode(person.orcid, "url")
        authors.append(author)
    if authors:
        data["authors"] = authors
    return "# Incomplete metadata template: review dependencies and compat bounds.\n" + tomlkit.dumps(data)


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

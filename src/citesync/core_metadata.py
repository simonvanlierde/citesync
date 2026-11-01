"""Read distribution headers into the existing PEP 621 field shapes, without loading package code."""

import csv
import unicodedata
from email.header import decode_header, make_header
from email.message import Message
from email.parser import Parser
from email.policy import compat32
from email.utils import getaddresses
from typing import Any

from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression
from packaging.utils import InvalidName, canonicalize_name
from packaging.version import InvalidVersion, Version

from citesync.errors import UnreadableError


def parse(text: str, rel: str) -> dict[str, Any]:  # noqa: C901 - independent optional headers
    """Normalize UTF-8 Core Metadata 1.x to 2.6; retain import notices for fields that cannot be represented.

    Repeated author/address and Project-URL headers are read in full. Conflicting
    scalar fields and repeated URL labels are errors. No build or package import runs.
    """
    message = Parser(policy=compat32).parsestr(text)
    if message.defects:
        raise UnreadableError(rel, f"malformed metadata headers: {type(message.defects[0]).__name__}")

    def one(key: str, *, required: bool = False) -> str:
        values = message.get_all(key, [])
        if len(values) > 1:
            raise UnreadableError(rel, f"{key} must appear only once")
        value = str(values[0]).strip() if values else ""
        if required and not value:
            raise UnreadableError(rel, f"missing {key} header")
        return value

    version = one("Metadata-Version", required=True)
    if version not in {"1.0", "1.1", "1.2", "2.1", "2.2", "2.3", "2.4", "2.5", "2.6"}:
        raise UnreadableError(rel, f"unsupported Metadata-Version {version!r}; citesync reads 1.0 to 2.6")
    project: dict[str, Any] = {"name": one("Name", required=True), "version": one("Version", required=True)}
    try:
        canonicalize_name(project["name"], validate=True)
        Version(project["version"])
    except (InvalidName, InvalidVersion) as err:
        raise UnreadableError(rel, f"invalid Name or Version: {err}") from err
    description = one("Summary") or one("Description") or message.get_payload()
    if isinstance(description, str) and description.strip():
        project["description"] = description.strip()
    if authors := _authors(message, rel):
        project["authors"] = authors
    if urls := _urls(message, rel):
        project["urls"] = urls
    if words := one("Keywords"):
        project["keywords"] = [word.strip() for word in words.split(",") if word.strip()]
    notes = _license(project, one("License-Expression"), one("License"), rel)
    return {"project": project, "build-system": {}, "_import_notes": notes}


def _license(project: dict[str, Any], expression: str, legacy: str, rel: str) -> list[tuple[str, str]]:
    notes = []
    if expression or legacy:
        try:
            canonical = canonicalize_license_expression(expression or legacy)
            if "LicenseRef-" in canonical:
                notes.append(
                    ("license", "LicenseRef has no public SPDX licence URL; review this licence in each citation file.")
                )
            else:
                project["license"] = canonical
        except InvalidLicenseExpression as err:
            if expression:
                raise UnreadableError(rel, f"invalid License-Expression: {err}") from err
            notes.append(
                (
                    "license",
                    "Legacy License text is not an SPDX expression; set License-Expression before converting it.",
                )
            )
    return notes


def _authors(message: Message, rel: str) -> list[dict[str, str]]:
    contacts: dict[str, dict[str, str]] = {}
    for raw_name, address in getaddresses(message.get_all("Author-email", [])):
        if not address or "@" not in address or any(c.isspace() for c in address):
            raise UnreadableError(rel, "Author-email must contain valid addresses with optional display names")
        if raw_name:
            name = _header(raw_name, rel)
            key = name.casefold()
            if key in contacts and contacts[key].get("email") != address:
                raise UnreadableError(rel, f"Author-email gives conflicting addresses for {name!r}")
            contacts[key] = {"name": name, "email": address}
    authors: dict[str, dict[str, str]] = {}
    for header in message.get_all("Author", []):
        try:
            names = next(csv.reader([_header(str(header), rel)], skipinitialspace=True, strict=True))
        except csv.Error as err:
            raise UnreadableError(rel, f"cannot read Author names: {err}") from err
        for raw_name in names:
            name = raw_name.strip()
            if name:
                authors.setdefault(name.casefold(), contacts.get(name.casefold(), {"name": name}))
    for key, contact in contacts.items():
        authors.setdefault(key, contact)
    return list(authors.values())


def _urls(message: Message, rel: str) -> dict[str, str]:
    urls = {}
    for raw in message.get_all("Project-URL", []):
        label, separator, address = str(raw).partition(",")
        label, address = label.strip(), address.strip()
        if not separator or not label or not address:
            raise UnreadableError(rel, "Project-URL must contain a label, comma and URL")
        if label in urls and urls[label] != address:
            raise UnreadableError(rel, f"Project-URL has conflicting values for {label!r}")
        urls[label] = address
    homes = message.get_all("Home-page", [])
    if len(homes) > 1:
        raise UnreadableError(rel, "Home-page must appear only once")
    if homes:
        urls.setdefault("Homepage", str(homes[0]).strip())
    return urls


def _header(value: str, rel: str) -> str:
    try:
        return unicodedata.normalize("NFC", " ".join(str(make_header(decode_header(value))).split()))
    except (LookupError, UnicodeError) as err:
        raise UnreadableError(rel, f"invalid encoded author header: {err}") from err

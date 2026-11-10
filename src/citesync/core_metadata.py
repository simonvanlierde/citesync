"""Read distribution headers in their own shape, for the pkg-info rows, without loading package code."""

import csv
import re
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
    """UTF-8 Core Metadata 1.0 to 2.6 as header names to values, with import notices for values left out.

    A multi-value header is a list: ``Author`` holds each name, ``Author-email`` the
    ``Name <address>`` contacts not already named in ``Author``, and ``Project-URL``
    ``{"label", "url"}`` objects with labels normalised as the well-known project URLs
    spec compares them. Conflicting scalar fields and URL labels are errors. No build or
    package import runs.
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
    headers: dict[str, Any] = {
        "Metadata-Version": version,
        "Name": one("Name", required=True),
        "Version": one("Version", required=True),
    }
    try:
        canonicalize_name(headers["Name"], validate=True)
        Version(headers["Version"])
    except (InvalidName, InvalidVersion) as err:
        raise UnreadableError(rel, f"invalid Name or Version: {err}") from err
    if summary := one("Summary"):  # Description and the body hold the README, not a summary
        headers["Summary"] = summary
    headers.update(_authors(message, rel))
    if urls := _urls(message, rel):
        headers["Project-URL"] = urls
    homes = message.get_all("Home-page", [])
    if len(homes) > 1:
        raise UnreadableError(rel, "Home-page must appear only once")
    if homes:
        headers["Home-page"] = str(homes[0]).strip()
    if words := one("Keywords"):
        headers["Keywords"] = [word.strip() for word in words.split(",") if word.strip()]
    notes = _license(headers, one("License-Expression"), one("License"), rel)
    return {**headers, "_import_notes": notes}


def _license(headers: dict[str, Any], expression: str, legacy: str, rel: str) -> list[tuple[str, str]]:
    """Set the licence header given as its canonical SPDX expression, or leave it out with a note."""
    notes = []
    if expression or legacy:
        try:
            canonical = canonicalize_license_expression(expression or legacy)
            if "LicenseRef-" in canonical:
                notes.append(
                    ("license", "LicenseRef has no public SPDX licence URL; review this licence in each citation file.")
                )
            else:
                headers["License-Expression" if expression else "License"] = canonical
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


def _authors(message: Message, rel: str) -> dict[str, list[str]]:
    """``Author`` and ``Author-email``, merged by name: a contact named in ``Author`` is that author, not a second one.

    An address with no name names no one, so it is left out.
    """
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
    authors: dict[str, str] = {}
    for header in message.get_all("Author", []):
        try:
            names = next(csv.reader([_header(str(header), rel)], skipinitialspace=True, strict=True))
        except csv.Error as err:
            raise UnreadableError(rel, f"cannot read Author names: {err}") from err
        for name in _names(names):
            authors.setdefault(name.casefold(), name)
    # NOTE: only the name; an address would reach the name decoder and end up in family-names
    emails = [c["name"] for key, c in contacts.items() if key not in authors]
    return {k: v for k, v in (("Author", list(authors.values())), ("Author-email", emails)) if v}


def _urls(message: Message, rel: str) -> list[dict[str, str]]:
    """Each Project-URL once, as ``{"label", "url"}``."""
    urls: dict[str, str] = {}
    for raw in message.get_all("Project-URL", []):
        label, separator, address = str(raw).partition(",")
        label, address = label.strip(), address.strip()
        if not separator or not label or not address:
            raise UnreadableError(rel, "Project-URL must contain a label, comma and URL")
        key = "".join(c for c in label.lower() if c.isalnum())  # as the well-known project URLs spec compares them
        if key in urls and urls[key] != address:
            raise UnreadableError(rel, f"Project-URL has conflicting values for {label!r}")
        urls[key] = address
    return [{"label": label, "url": url} for label, url in urls.items()]


_SUFFIX = re.compile(r"(?:inc|llc|ltd|gmbh|pbc|corp)\.?", re.IGNORECASE)
_ET_AL = re.compile(r"et al\.?", re.IGNORECASE)


def _names(pieces: list[str]) -> list[str]:
    """``Author`` pieces split at commas as names: a company suffix rejoins the piece before it, and "et al." goes."""
    names: list[str] = []
    for piece in (p.strip() for p in pieces):
        if names and _SUFFIX.fullmatch(piece):
            names[-1] = f"{names[-1]}, {piece}"
        elif piece and not _ET_AL.fullmatch(piece):
            names.append(piece)
    return names


def _header(value: str, rel: str) -> str:
    try:
        return unicodedata.normalize("NFC", " ".join(str(make_header(decode_header(value))).split()))
    except (LookupError, UnicodeError) as err:
        raise UnreadableError(rel, f"invalid encoded author header: {err}") from err

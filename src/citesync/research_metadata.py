"""Read R DESCRIPTION and Julia Project.toml files in their own shape, for the r-description and julia rows."""

import ast
import re
import tomllib
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

from packaging.licenses import InvalidLicenseExpression, canonicalize_license_expression

from citesync.errors import UnreadableError
from citesync.formats import codemeta_orcid


def parse(text: str, rel: str) -> dict[str, Any]:
    """Read static DESCRIPTION or Project.toml text; never run R, Julia or package code.

    A DESCRIPTION reads as its DCF fields, with ``Authors@R`` as a list of
    ``{"given", "family", "role", "comment": {"ORCID"}}`` people. A Project.toml reads as
    its TOML, checked. Values a citation can't use are left out with an import notice.
    """
    notes: list[tuple[str, str]] = []
    data = _r(text, rel, notes) if rel.rsplit("/", 1)[-1] == "DESCRIPTION" else _julia(text, rel)
    data["_import_notes"] = notes
    return data


def _text(value: object, field: str, rel: str) -> str:
    if not isinstance(value, str):
        raise UnreadableError(rel, f"{field} must be text")
    return value.strip()


def _licence(value: str, notes: list[tuple[str, str]]) -> str | None:
    """An R License field as an SPDX expression, or None and a note when it can't be one."""
    if not value:
        return None
    aliases = {"BSD_2_clause": "BSD-2-Clause", "BSD_3_clause": "BSD-3-Clause"}
    value = " OR ".join(aliases.get(part.strip(), part.strip()) for part in value.split("|"))
    value = re.sub(
        r"\b(GPL|LGPL|AGPL)\s*\(\s*(>=|==)\s*(\d+(?:\.\d+)?)\s*\)",
        lambda m: f"{m[1]}-{m[3] if '.' in m[3] else m[3] + '.0'}-{'or-later' if m[2] == '>=' else 'only'}",
        value,
    )
    value = re.sub(
        r"\b(GPL|LGPL|AGPL)-(\d+(?:\.\d+)?)(?![\w.-])",
        lambda m: f"{m[1]}-{m[2] if '.' in m[2] else m[2] + '.0'}-only",
        value,
    )
    try:
        expression = canonicalize_license_expression(value)
    except InvalidLicenseExpression:
        expression = ""
    if expression and "LicenseRef-" not in expression:
        return expression
    notes.append(
        ("license", "The licence needs review: use an explicit SPDX expression; external licence files are not read.")
    )
    return None


def _orcid(value: object, rel: str) -> str:
    orcid = codemeta_orcid(value)
    if not orcid:
        raise UnreadableError(rel, "author ORCID must be an ORCID iD or URL")
    return "https://orcid.org/" + orcid


def _julia(text: str, rel: str) -> dict[str, Any]:  # noqa: C901, PLR0912 - validate each optional field and author shape
    try:
        raw = tomllib.loads(text)
    except tomllib.TOMLDecodeError as err:
        raise UnreadableError(rel, str(err)) from err
    for key in ("name", "version"):
        if key in raw:
            _text(raw[key], key, rel)
    if "uuid" in raw:
        try:
            UUID(_text(raw["uuid"], "uuid", rel))
        except ValueError as err:
            raise UnreadableError(rel, "uuid must be a Julia package UUID") from err
    authors = raw.get("authors", [])
    if not isinstance(authors, list):
        raise UnreadableError(rel, "authors must be an array of names or CFF person/entity tables")
    for author in authors:
        if isinstance(author, str):
            if not re.sub(r"\s*<[^<>]+>\s*$", "", author).strip():
                raise UnreadableError(rel, "author must have a name")
        elif isinstance(author, dict):
            fields = {
                key: _text(value, f"author {key}", rel)
                for key, value in author.items()
                if key in {"given-names", "family-names", "name", "name-particle", "name-suffix", "orcid"}
            }
            if fields.get("name") and (fields.get("given-names") or fields.get("family-names")):
                raise UnreadableError(rel, "author must be a CFF person or entity, not both")
            if not any(fields.get(k) for k in ("name", "given-names", "family-names")):
                raise UnreadableError(rel, "author table needs a name")
            if fields.get("orcid"):
                _orcid(fields["orcid"], rel)
        else:
            raise UnreadableError(rel, "author must be a name or CFF person/entity table")
    return raw


def _dcf(text: str, rel: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    key = ""
    ended = False
    for line in text.splitlines():
        if not line.strip():
            ended = bool(fields)
            continue
        if ended:
            raise UnreadableError(rel, "DESCRIPTION must contain a single DCF record")
        if line[0].isspace():
            if not key:
                raise UnreadableError(rel, "DESCRIPTION continuation has no field")
            fields[key] += " " + line.strip()
        else:
            match = re.fullmatch(r"([A-Za-z][A-Za-z0-9@.-]*):\s*(.*)", line)
            if not match or match[1] in fields:
                raise UnreadableError(rel, "DESCRIPTION needs unique Field: value lines")
            key = match[1]
            fields[key] = match[2]
    return fields


@dataclass
class _Call:
    name: str
    arguments: list[tuple[str | None, Any]]


_TOKEN = re.compile(r"""\s*("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z][A-Za-z0-9_.]*|[(),=])""")


def _expression(text: str, rel: str) -> _Call:  # noqa: C901 - bounded literal grammar and error cases
    text = text.strip()
    tokens = []
    position = 0
    while position < len(text):
        match = _TOKEN.match(text, position)
        if not match:
            raise UnreadableError(rel, "Authors@R supports only literal person(), c(), strings and NULL")
        tokens.append(match[1])
        position = match.end()
    index = 0

    def value(depth: int = 0) -> Any:  # noqa: ANN401 - bounded literal syntax tree
        nonlocal index
        if depth > 16 or index >= len(tokens):
            raise ValueError
        lexeme = tokens[index]
        index += 1
        if lexeme.startswith(('"', "'")):
            literal = ast.literal_eval(lexeme)
            literal.encode("utf-8")
            return literal
        if lexeme == "NULL":
            return None
        if lexeme not in {"person", "c"} or index >= len(tokens) or tokens[index] != "(":
            raise ValueError
        index += 1
        arguments = []
        while index < len(tokens) and tokens[index] != ")":
            key = None
            if index + 1 < len(tokens) and tokens[index + 1] == "=":
                key = tokens[index]
                index += 2
            arguments.append((key, value(depth + 1)))
            if index < len(tokens) and tokens[index] == ",":
                index += 1
            elif index >= len(tokens) or tokens[index] != ")":
                raise ValueError
        if index >= len(tokens):
            raise ValueError
        index += 1
        return _Call(lexeme, arguments)

    try:
        result = value()
        if index != len(tokens) or not isinstance(result, _Call):
            raise ValueError  # noqa: TRY301 - use the same public grammar error
    except (ValueError, SyntaxError, RecursionError, UnicodeError) as err:
        raise UnreadableError(rel, "Authors@R supports only bounded, literal person() and c() calls") from err
    return result


def _strings(value: Any, rel: str) -> list[str]:  # noqa: ANN401 - literal syntax tree
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, _Call) and value.name == "c" and all(k is None for k, _ in value.arguments):
        return [item for _, child in value.arguments for item in _strings(child, rel)]
    raise UnreadableError(rel, "Authors@R person fields must be strings, c(strings), or NULL")


def _r_people(call: _Call, rel: str, notes: list[tuple[str, str]]) -> list[dict[str, Any]]:  # noqa: C901, PLR0912 - person fields, role and ORCID variants
    if call.name == "c":
        people = []
        for key, child in call.arguments:
            if key is not None or not isinstance(child, _Call):
                raise UnreadableError(rel, "Authors@R c() must contain literal person() calls")
            people += _r_people(child, rel, notes)
        return people
    fields: dict[str, Any] = {}
    positional = iter(("given", "family"))
    for argument_name, value in call.arguments:
        key = argument_name if argument_name is not None else next(positional, "")
        if key not in {"given", "family", "email", "role", "comment"} or key in fields:
            raise UnreadableError(rel, "Authors@R needs unique named person fields after given and family")
        fields[key] = value
    given, family = (" ".join(_strings(fields.get(k), rel)) for k in ("given", "family"))
    if not given and not family:
        raise UnreadableError(rel, "Authors@R person needs a name")
    person: dict[str, Any] = {k: v for k, v in (("given", given), ("family", family)) if v}
    comment = fields.get("comment")
    if isinstance(comment, _Call):
        if comment.name != "c" or any(k is None or not isinstance(v, str) for k, v in comment.arguments):
            raise UnreadableError(rel, 'Authors@R comment supports c(ORCID = "...")')
        identifiers = [v for k, v in comment.arguments if k == "ORCID"]
        if len(identifiers) > 1:
            raise UnreadableError(rel, "Authors@R repeats ORCID")
        if identifiers:
            person["comment"] = {"ORCID": _orcid(identifiers[0], rel)}
    elif comment is not None:
        _strings(comment, rel)
    _strings(fields.get("email"), rel)
    roles = _strings(fields.get("role"), rel)
    if "aut" in roles:  # an author who also contributed is one author, not a contributor too
        roles = [role for role in roles if role != "ctb"]
    elif "ctb" not in roles:
        notes.append(
            ("author", "A person without the R aut or ctb role was omitted; maintainer status alone is not authorship.")
        )
    return [{**person, "role": roles}]


def _r(text: str, rel: str, notes: list[tuple[str, str]]) -> dict[str, Any]:
    fields = _dcf(text, rel)
    encoding = fields.get("Encoding", "UTF-8").lower().replace("_", "-")
    if encoding not in {"utf-8", "utf8", "ascii"}:
        raise UnreadableError(rel, "Save DESCRIPTION as UTF-8 and update Encoding before importing")
    package = fields.get("Package", "")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9.]*[A-Za-z0-9]", package):
        raise UnreadableError(rel, "DESCRIPTION needs a valid Package field")
    data: dict[str, Any] = dict(fields)
    data["Package"] = f"{package}: {fields['Title']}" if fields.get("Title") else package  # as cffr and codemetar
    if fields.get("Date") and not _r_date(fields["Date"], notes):
        del data["Date"]
    if "Authors@R" in fields:
        data["Authors@R"] = _r_people(_expression(fields["Authors@R"], rel), rel, notes)
    elif "Author" in fields or "Maintainer" in fields:
        notes.append(
            ("author", "Author and Maintainer prose is not parsed; supply literal Authors@R with explicit roles.")
        )
    if licence := _licence(fields.get("License", ""), notes):
        data["License"] = licence
    else:
        data.pop("License", None)
    urls = re.findall(r"https?://[^\s,]+", fields.get("URL", ""))
    repos = _repositories(urls, rel)
    data.pop("URL", None)
    if len(set(repos)) == 1:
        data["URL"] = repos[0]
    elif urls:
        notes.append(
            ("codeRepository", "URL does not identify one supported repository URL; review the repository field.")
        )
    return data


def _r_date(value: str, notes: list[tuple[str, str]]) -> str | None:
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is not None and parsed.isoformat() == value:
        return value
    notes.append(("datePublished", "Use an ISO date (YYYY-MM-DD); the R Date value was omitted."))
    return None


def _repositories(urls: list[str], rel: str) -> list[str]:
    repos = []
    for url in urls:
        try:
            parsed = urlsplit(url)
        except ValueError as err:
            raise UnreadableError(rel, "URL contains an invalid repository address") from err
        if (
            parsed.hostname in {"github.com", "gitlab.com", "codeberg.org", "bitbucket.org"}
            and len(parsed.path.strip("/").split("/")) == 2
        ):
            repos.append(url)
    return repos

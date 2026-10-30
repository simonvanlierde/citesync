"""Rewrite the files that disagree with the source, changing only what check reports.

Each file is edited in a form that keeps the rest of it as it was: CFF through
ruamel.yaml's round trip (comments, key order, quoting), TOML through tomlkit
(comments, layout), and JSON by splicing each changed value into the original
text (key order, indentation, inline arrays, trailing newline). Values are
spelled the way the target format spells them, through :mod:`citesync.codecs`.
"""

import copy
import datetime as dt
import io
import json
import os
import re
import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import tomlkit
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import ScalarString
from ruamel.yaml.util import load_yaml_guess_indent

from citesync import codecs
from citesync.check import Finding, cargo_keyword_key, findings, has_slot, keyword_key, missing, near_miss, read_docs
from citesync.config import Config
from citesync.errors import CannotWrite
from citesync.formats import (
    MANIFESTS,
    Doc,
    Person,
    cff_person,
    codemeta_person,
    codemeta_version,
    format_of,
    locate,
    person,
)
from citesync.mapping import PEOPLE, TERMS, Mapping, load_mapping, person_terms, relative

# The @context of a codemeta.json write creates when codemeta-version is unset: the version
# the project template renders and Software Heritage reads.
NEW_CODEMETA_VERSION = "3.0"


def write(
    root: Path, config: Config, mapping: Mapping | None = None, *, dry_run: bool = False
) -> tuple[dict[str, str], dict[tuple[str, str], str], list[Finding]]:
    """Write every finding write may fix; return what it wrote, why it skipped a field, and what it couldn't read.

    It fixes the findings check reports, less those config ``ignore`` lists: in a derived
    citation file every term, in a manifest only the terms in ``write-manifests``, and only
    where the source holds the term and is what the file was compared with. A field the file
    leaves out stays out. An unreadable file is never written. A value the file's format can't
    spell without losing something is left as it was, its (path, term) mapped to the reason.
    Every new text is made before any file is replaced, so an error leaves the files as they were.
    With ``dry_run``, nothing is replaced.

    Returns:
        The new text of each path it changed, the reason for each (path, term) it left as it was, and the
        ``unreadable`` findings.

    Raises:
        CheckError: as :func:`citesync.check.check` does.
    """
    mapping = mapping or load_mapping()
    docs, unreadable = read_docs(root, config, mapping)
    fix = {
        (f.file, f.term)
        for f in findings(docs, unreadable, config)
        if f.severity == "error" and f.rule not in config.ignore
    }
    source, texts, skipped = docs[0], {}, {}
    key = keyword_key(config)
    for doc in docs:  # the source too, for its @context
        terms = [
            t
            for t in TERMS
            if (doc.path, t) in fix
            and has_slot(source, t)  # else the others were compared with each other (D2): left alone
            and t in source.record
            and t in doc.record
            and (doc.is_citation or t in config.write_manifests)
        ]
        context = config.codemeta_version if (doc.path, "@context") in fix else None
        if not terms and not context:
            continue
        old = (root / doc.path).read_bytes().decode("utf-8")  # bytes, so CRLF line ends stay
        crlf = "\r\n" in old  # edited with LF line ends, which the YAML and JSON writers add
        new, reasons = _rewrite(doc, source, terms, old.replace("\r\n", "\n") if crlf else old, mapping, context, key)
        new = new.replace("\n", "\r\n") if crlf else new
        skipped |= {(doc.path, term): reason for term, reason in reasons.items()}
        if new != old:
            texts[doc.path] = new
    if "file-missing" not in config.ignore and "codemeta.json" in missing(root, config):
        texts["codemeta.json"] = _new_codemeta(source, config.codemeta_version or NEW_CODEMETA_VERSION, mapping, key)
    if not dry_run:
        _replace({root / rel: text for rel, text in texts.items()})
    return dict(sorted(texts.items())), skipped, [f for f in unreadable if f.rule == "unreadable"]


def advice(finding: Finding, config: Config, skipped: dict[tuple[str, str], str]) -> str:
    """What to do about a finding write left: why write skipped it, or that a manifest field can be opted in."""
    if (reason := skipped.get((str(finding.file), str(finding.term)))) is not None:
        return f"edit it by hand: {reason}"
    if (
        finding.file
        and finding.term
        and format_of(finding.file) in MANIFESTS.values()
        and finding.term not in config.write_manifests
    ):
        return f"edit it by hand, or add {finding.term} to write-manifests"
    return "edit it by hand"


def _replace(texts: dict[Path, str]) -> None:
    """Write each text to a temporary file beside its path, then move them all into place.

    A symlink's target is written, and the link stays. A failure before the moves leaves every
    file as it was; only a failed move (a rename within one directory) leaves earlier ones moved.
    """
    temps: dict[Path, Path] = {}
    try:
        for link, text in texts.items():
            path = link.resolve()
            fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
            temps[Path(name)] = path
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
                file.write(text)
            if path.exists():
                shutil.copymode(path, name)
            else:  # mkstemp's file is owner-only; a new file gets what open() would give it
                umask = os.umask(0)
                os.umask(umask)
                Path(name).chmod(0o666 & ~umask)
        for tmp, path in temps.items():
            tmp.replace(path)
    finally:
        for tmp in temps:
            tmp.unlink(missing_ok=True)  # moved ones are gone already


def _rewrite(
    doc: Doc,
    source: Doc,
    terms: list[str],
    text: str,
    mapping: Mapping,
    context: str | None,
    keyword_key: Callable[[str], str],
) -> tuple[str, dict[str, str]]:
    """``text`` with ``terms`` set from ``source``, and the reason for each term it left as it was."""
    if doc.format == "cff-1.2.0":
        yaml = _yaml(text)
        data = yaml.load(text)
        skipped = _apply(doc, source, terms, data, mapping, context, keyword_key)
        out = io.StringIO()
        yaml.dump(data, out)
        return out.getvalue(), skipped
    if doc.path.endswith(".toml"):
        data = tomlkit.parse(text)
        skipped = _apply(doc, source, terms, data, mapping, context, keyword_key)
        return tomlkit.dumps(data), skipped
    old = json.loads(text)
    data = copy.deepcopy(old)
    skipped = _apply(doc, source, terms, data, mapping, context, keyword_key)
    return _splice(text, old, data), skipped


def _new_codemeta(source: Doc, version: str, mapping: Mapping, keyword_key: Callable[[str], str]) -> str:
    """A codemeta.json holding each term the source has, spelled as codemeta spells it."""
    blank = {
        "name": "",
        "description": "",
        "version": "",
        "datePublished": "",
        "identifier": "https://doi.org/",  # the placeholders' shapes pick the forms: DOI and SPDX URLs
        "codeRepository": "",
        "license": "https://spdx.org/licenses/",
        "author": [],
        "contributor": [],
        "keywords": [],
    }
    terms = [t for t in blank if t in source.record]
    data: dict[str, Any] = {"@context": f"https://w3id.org/codemeta/{version}", "@type": "SoftwareSourceCode"}
    data |= {t: blank[t] for t in terms}
    doc = Doc("codemeta.json", "codemeta", {}, frozenset(), version, release=True)
    _apply(doc, source, terms, data, mapping, None, keyword_key)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def _yaml(text: str) -> YAML:
    """A round-trip YAML set to the file's own indentation, with no line wrapping."""
    _, indent, offset = load_yaml_guess_indent(text)
    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 1 << 16
    yaml.explicit_start = bool(re.search(r"^---", text, re.MULTILINE))
    if indent:
        yaml.indent(mapping=max(indent - (offset or 0), 2), sequence=indent, offset=offset or 0)
    return yaml


def _apply(
    doc: Doc,
    source: Doc,
    terms: list[str],
    data: Any,  # noqa: ANN401
    mapping: Mapping,
    context: str | None,
    keyword_key: Callable[[str], str],
) -> dict[str, str]:
    skipped = {}
    if context:
        iri = f"https://w3id.org/codemeta/{context}"
        old = data["@context"]
        data["@context"] = [iri if codemeta_version(c) else c for c in old] if isinstance(old, list) else iri
    for term in terms:
        path = mapping[doc.format, term]
        assert path is not None  # noqa: S101 - write() only passes terms the file holds
        slot = locate(doc.format, term, data, path)
        if slot is None:
            continue
        container, key = slot
        old = container[key]
        if isinstance(old, dict) and old.get("workspace") is True:
            continue  # Cargo inherits it from [workspace.package]: edit it there by hand
        try:
            if term in PEOPLE:
                new = _people(doc.format, old, source, path, mapping, term)
            else:
                new = _encode(doc, source, term, source.record[term], old, keyword_key)
        except CannotWrite as err:
            skipped[term] = str(err)
            continue
        if new is not old:
            _set(container, key, _styled(new, old), old)
    return skipped


def _encode(doc: Doc, source: Doc, term: str, value: Any, old: Any, keyword_key: Callable[[str], str]) -> Any:  # noqa: ANN401, C901, PLR0911 - one branch per term
    """``value`` spelled for ``doc``'s format, in the shape ``old`` has; ``keyword_key`` compares keywords."""
    fmt = doc.format
    if term == "version":
        if fmt in {"cargo", "npm"}:
            return codecs.version_encode_semver(value)
        if fmt == "pep621":
            if isinstance(key := codecs.version_key(value), str):
                msg = f"{value} is not a PEP 440 version"
                raise CannotWrite(msg)
            return str(key)
        return value
    if term == "license":
        return _license(fmt, value, old)
    if term == "identifier":
        return _identifier(value, old)
    if term == "codeRepository":
        if isinstance(old, dict):  # npm's {type, url}
            old["url"] = _encode(doc, source, term, value, old["url"], keyword_key)
            return old
        old = old.strip()
        return ("git+" if old.startswith("git+") else "") + value + (".git" if old.endswith(".git") else "")
    if term == "datePublished":
        return _date(value, old)
    if term == "keywords":
        key = cargo_keyword_key(keyword_key, doc, source)
        return _keywords(old, value, key, add=doc.is_citation, remove=source.is_citation or not doc.is_citation)
    return value


def _date(value: str, old: Any) -> Any:  # noqa: ANN401
    """``value`` as CFF, CodeMeta and Zenodo all take it, ``YYYY-MM-DD``; an unquoted CFF date stays a YAML date.

    Raises:
        CannotWrite: when ``value`` is not such a date.
    """
    try:
        day = dt.date.fromisoformat(value)
    except ValueError as err:
        msg = f"{value} is not a YYYY-MM-DD date"
        raise CannotWrite(msg) from err
    return day if isinstance(old, dt.date) else day.isoformat()


def _identifier(doi: str, old: Any) -> Any:  # noqa: ANN401
    """``doi`` in ``old``'s form: a DOI URL or bare, in place inside a codemeta list or PropertyValue."""
    if isinstance(old, list):  # codemeta: the first DOI in the list is the one read
        i = next(i for i, el in enumerate(old) if codecs.doi_decode(el))
        return [*old[:i], _identifier(doi, old[i]), *old[i + 1 :]]
    if isinstance(old, dict):  # a schema.org PropertyValue: set the keys holding the DOI, keep the rest
        for key in ("value", "url"):
            if codecs.doi_decode(old.get(key)):
                old[key] = _identifier(doi, old[key])
        return old
    form = "url" if isinstance(old, str) and old.strip().lower().startswith("http") else "bare"
    return codecs.doi_encode(doi, form)


def _license(fmt: str, spdx: str, old: Any) -> Any:  # noqa: ANN401
    """CFF and codemeta write ``A OR B`` as a list, codemeta as SPDX URLs where the file does.

    Raises:
        CannotWrite: for any compound expression in Zenodo, and ``AND`` or ``WITH`` in CFF and codemeta.
    """
    operators = set(spdx.split()) & {"AND", "OR", "WITH"}
    if fmt == "zenodo" and operators:
        msg = "Zenodo takes one licence id"
        raise CannotWrite(msg)
    if fmt == "zenodo":
        return codecs.license_encode(spdx, "zenodo")
    if isinstance(old, dict) and "text" in old:  # PEP 621's legacy {text = ...}
        old["text"] = spdx
        return old
    if fmt not in {"cff-1.2.0", "codemeta"}:
        return spdx
    if operators - {"OR"}:
        msg = "a licence list can only say OR, not AND or WITH"
        raise CannotWrite(msg)
    first = old[0] if isinstance(old, list) and old else old
    form = "spdx-url" if isinstance(first, str) and first.startswith("http") else "spdx"
    ids = [codecs.license_encode(i, form) for i in spdx.replace("(", "").replace(")", "").split(" OR ")]
    return ids if len(ids) > 1 or isinstance(old, list) else ids[0]


def _keywords(old: Any, value: tuple[str, ...], key: Callable[[str], str], *, add: bool, remove: bool) -> Any:  # noqa: ANN401
    """``old`` with the words not in ``value`` removed, and those missing added at the end, as the rule asks.

    Words compare by ``key``.

    Between citation files the sets must be equal (both); a manifest's must be a
    subset of a citation file's, so only the manifest loses words, or only the citation file gains them.
    """
    items = old if isinstance(old, list) else [old]
    want = set(map(key, value))
    for i, word in enumerate(items):  # a near miss takes the source's spelling where it stands
        if (near := near_miss(str(word), value, key)) and key(near) not in {key(str(k)) for k in items}:
            items[i] = _styled(near, word)
    if remove:
        for i in reversed(range(len(items))):
            if key(str(items[i])) not in want:
                del items[i]
    if add:
        have = {key(str(k)) for k in items}
        items.extend(_styled(k, items[0] if items else None) for k in value if key(k) not in have)
    return items


def _people(fmt: str, old: Any, source: Doc, path: str, mapping: Mapping, term: str) -> Any:  # noqa: ANN401
    """``term``'s list for ``fmt``, with the source's people in the source's order.

    An existing entry is kept, with its other fields, when its name or ORCID
    matches; it is renamed on an ORCID match and gets the source's ORCID where
    both have one. Anyone else becomes a new entry, so an email or affiliation
    never moves to a different person. Entries with no name or ORCID stay, at the
    end. npm keeps one author, so only the first is set and the rest stay.

    Raises:
        CannotWrite: when an entry it would drop holds more than a name and ORCID, or when a
            Zenodo contributor would be added, since Zenodo needs a contributor type.
    """
    items = list(old) if isinstance(old, list) else [old]
    decoded = [_decode(fmt, el, path, mapping, term) for el in items]
    npm = term == "author" and "npm" in {fmt, source.format}
    people: tuple[Person, ...] = source.record[term][:1] if npm else source.record[term]
    matches = _matches(decoded, people)
    used = {i for i in matches if i is not None}
    if fmt == "zenodo" and term == "contributor" and None in matches:
        msg = "Zenodo needs a type for each contributor, which citesync doesn't choose"
        raise CannotWrite(msg)
    kept = {matches[0]} if npm and fmt == "npm" else {i for i, q in enumerate(decoded) if i in used or npm or q is None}
    for i, el in enumerate(items):  # before any entry changes, so a skipped field stays as it was
        if i not in kept and (extra := _extra(fmt, el, path, mapping, term)):
            q = decoded[i]
            msg = f"renaming would drop the {extra} of {(q.name if q and q.name else el)!r}"
            raise CannotWrite(msg)
    out = []
    for p, i in zip(people, matches, strict=True):
        if i is None:
            out.append(_new_person(fmt, p, path, mapping, items[0] if items else None, term))
            continue
        q = decoded[i]
        assert q is not None  # noqa: S101 - _match skips entries that read as no one
        if codecs.name_key(q.name or "") != codecs.name_key(p.name or ""):
            _rename(fmt, items[i], p, path, mapping, term)
        if q.orcid and p.orcid and q.orcid != p.orcid:
            okey = relative(str(mapping[fmt, f"{term}.@id"]), path)
            items[i][okey] = _styled(_fields(fmt, p, path, mapping, term)[okey], items[i][okey])
        out.append(items[i])
    out += [el for i, el in enumerate(items) if i not in used and (npm or decoded[i] is None)]
    if not isinstance(old, list):
        return out[0] if len(out) == 1 or fmt == "npm" else out
    _relist(old, out)
    return old


def _extra(fmt: str, element: Any, path: str, mapping: Mapping, term: str) -> str | None:  # noqa: ANN401
    """What an author entry holds besides a name and ORCID: a key, or an npm or Cargo string's email or url."""
    if isinstance(element, str):
        return "email" if "<" in element else "url" if "(" in element else None
    if not isinstance(element, dict):
        return None
    names = {relative(at, path) for t in person_terms(term) if (at := mapping[fmt, t])}
    return next((str(k) for k in element if k not in names | {"@type", "name", "name-particle", "name-suffix"}), None)


def _relist(old: list[Any], new: list[Any]) -> None:
    """Make ``old`` hold ``new``'s elements in place, by deletes and appends where that will do.

    In place keeps the list's own layout (a multi-line TOML array, a YAML sequence's comments).
    """
    kept = [el for el in old if any(el is n for n in new)]
    if len(kept) <= len(new) and all(a is b for a, b in zip(kept, new, strict=False)):
        for i in reversed(range(len(old))):
            if not any(old[i] is n for n in kept):
                del old[i]
        old.extend(new[len(kept) :])
    else:  # a reorder: rebuild the list
        old.clear()
        old.extend(new)


def _decode(fmt: str, element: Any, path: str, mapping: Mapping, term: str) -> Person | None:  # noqa: ANN401
    if fmt == "cff-1.2.0" and isinstance(element, dict):
        element = cff_person(element)
    elif fmt == "codemeta":
        element = codemeta_person(element)
    elif fmt == "npm" and isinstance(element, str):
        element = {"name": element}
    return person(fmt, element, path, mapping, term)


def _matches(decoded: list[Person | None], people: tuple[Person, ...]) -> list[int | None]:
    """For each of ``people`` in turn, the entry of ``decoded`` it matches, each entry used once."""
    used: set[int] = set()
    matches = []
    for p in people:
        matches.append(i := _match(decoded, used, p))
        if i is not None:
            used.add(i)
    return matches


def _match(decoded: list[Person | None], used: set[int], p: Person) -> int | None:
    """The first unused entry with ``p``'s name, else the first with ``p``'s ORCID."""
    free = [(i, q) for i, q in enumerate(decoded) if q is not None and i not in used]
    by_name = (i for i, q in free if p.name and codecs.name_key(q.name or "") == codecs.name_key(p.name))
    by_orcid = (i for i, q in free if p.orcid and q.orcid == p.orcid)
    return next(by_name, next(by_orcid, None))


def _fields(fmt: str, p: Person, path: str, mapping: Mapping, term: str) -> dict[str, str]:
    """A person's name and ORCID under the keys ``fmt`` keeps them in."""
    gkey, fkey, okey = (relative(at, path) if (at := mapping[fmt, t]) else None for t in person_terms(term))
    given, family = p.given, p.family
    if family is None:  # shortcut: from a one-string name the last word is the family name; fix by hand if not
        rest, _, family = (p.name or "").rpartition(" ")
        given = rest or None
    if gkey == fkey:
        fields = {gkey: codecs.zenodo_name_encode(given, family) if fmt == "zenodo" else p.name}
    else:
        fields = {gkey: given, fkey: family}
    if okey and p.orcid:
        fields[okey] = codecs.orcid_encode(p.orcid, "bare" if fmt == "zenodo" else "url")
    return {str(k): v for k, v in fields.items() if v}


def _new_person(fmt: str, p: Person, path: str, mapping: Mapping, like: Any, term: str) -> Any:  # noqa: ANN401
    fields = _fields(fmt, p, path, mapping, term)
    if fmt == "cargo" or (fmt == "npm" and not isinstance(like, dict)):
        return p.name or ""
    if fmt == "pep621":
        table = tomlkit.inline_table()
        table.update(fields)
        return table
    if p.organization and fmt in {"codemeta", "cff-1.2.0"}:
        return {"@type": "Organization", "name": p.name} if fmt == "codemeta" else CommentedMap(name=p.name)
    if fmt == "codemeta":
        return {"@type": "Person", **fields}
    if fmt == "cff-1.2.0":
        return CommentedMap((k, _styled(v, like.get(k) if isinstance(like, dict) else None)) for k, v in fields.items())
    return fields


def _rename(fmt: str, element: Any, p: Person, path: str, mapping: Mapping, term: str) -> None:  # noqa: ANN401
    """Set the name of an entry matched by ORCID, in place; only the citation files have ORCIDs."""
    fields = _fields(fmt, p, path, mapping, term)
    if fmt == "codemeta" and codemeta_person(element) is not element:  # a name-only entry keeps its one name
        element["name"] = p.name
        return
    if fmt == "cff-1.2.0":
        for key in ("name-particle", "name-suffix"):
            element.pop(key, None)  # folded into family-names by now
    for key in {relative(str(mapping[fmt, t]), path) for t in person_terms(term)[:2]}:
        if key in fields:
            element[key] = _styled(fields[key], element.get(key))
        else:
            element.pop(key, None)


def _set(container: Any, key: str, new: Any, old: Any) -> None:  # noqa: ANN401
    """``container[key] = new``, moving a YAML end-of-line comment by as much as the value grew."""
    container[key] = new
    comment = getattr(container, "ca", None) and container.ca.items.get(key)
    if comment and comment[2] is not None and isinstance(old, str) and isinstance(new, str):
        comment[2].column = max(comment[2].column + len(new) - len(old), 0)


def _styled(new: Any, old: Any) -> Any:  # noqa: ANN401
    """``new`` in ``old``'s YAML quoting style, so a quoted CFF value stays quoted."""
    if isinstance(old, ScalarString) and isinstance(new, str) and not isinstance(new, ScalarString):
        return type(old)(new)
    return new


# JSON: splice changed values into the original text, so everything else keeps its bytes.

_DECODER = json.JSONDecoder()


def _skip(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def _node(text: str, i: int) -> tuple[int, int, dict[Any, Any] | None]:
    """The (start, end, children) of the JSON value at ``i``; children by key or index, None for a scalar."""
    i = _skip(text, i)
    opener = text[i]
    if opener not in "[{":
        return i, _DECODER.raw_decode(text, i)[1], None
    kids: dict[Any, Any] = {}
    j = i + 1
    while True:
        j = _skip(text, j)
        if text[j] in "]}":
            return i, j + 1, kids
        if opener == "{":
            key, end = _DECODER.raw_decode(text, j)
            j = _skip(text, end) + 1  # past the colon
        else:
            key = len(kids)
        kids[key] = _node(text, j)
        j = _skip(text, kids[key][1])
        j += text[j] == ","


def _splice(text: str, old: Any, new: Any) -> str:  # noqa: ANN401
    indent = re.search(r"\n([ \t]+)\S", text)
    edits: list[tuple[int, int, str]] = []
    _diff(text, _node(text, 0), old, new, edits, indent[1] if indent else "  ")
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def _diff(text: str, node: tuple[int, int, Any], old: Any, new: Any, edits: list, indent: str) -> None:  # noqa: ANN401
    """Collect a replacement for each smallest value that differs between ``old`` and ``new``."""
    start, end, kids = node
    if type(old) is type(new) and old == new:
        return
    if isinstance(old, dict) and isinstance(new, dict) and list(old) == list(new):
        for key in old:
            _diff(text, kids[key], old[key], new[key], edits, indent)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for i, (a, b) in enumerate(zip(old, new, strict=True)):
            _diff(text, kids[i], a, b, edits, indent)
    elif isinstance(old, list) and isinstance(new, list) and old and new[: len(old)] == old:
        # appended to: add after the last element in its layout, leaving the others' text alone
        last_start, last_end, _ = kids[len(old) - 1]
        line = text[text.rfind("\n", 0, last_start) + 1 :]
        margin = line[: len(line) - len(line.lstrip(" \t"))]
        sep = ",\n" + margin if "\n" in text[start:end] else ", "
        multi = "\n" in text[last_start:last_end]
        dumped = (json.dumps(el, indent=indent if multi else None, ensure_ascii=False) for el in new[len(old) :])
        edits.append((last_end, last_end, "".join(sep + d.replace("\n", "\n" + margin) for d in dumped)))
    elif "\n" in text[start:end]:  # a multi-line value stays multi-line, at the indentation of its line
        line = text[text.rfind("\n", 0, start) + 1 :]
        margin = line[: len(line) - len(line.lstrip(" \t"))]
        edits.append((start, end, json.dumps(new, indent=indent, ensure_ascii=False).replace("\n", "\n" + margin)))
    else:
        edits.append((start, end, json.dumps(new, ensure_ascii=False)))

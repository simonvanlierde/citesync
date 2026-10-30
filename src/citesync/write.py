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
from dataclasses import replace
from pathlib import Path
from typing import Any

import tomlkit
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap
from ruamel.yaml.scalarstring import ScalarString
from ruamel.yaml.util import load_yaml_guess_indent

from citesync import codecs
from citesync.check import Finding, cargo_keyword_key, findings, has_slot, keyword_key, missing, near_misses, read_docs
from citesync.config import Config
from citesync.errors import CannotWrite, CheckError
from citesync.formats import (
    CITATION_FILES,
    MANIFESTS,
    Doc,
    Person,
    cff_person,
    codemeta_person,
    codemeta_version,
    format_of,
    inside,
    locate,
    person,
    same_name,
)
from citesync.jsonsplice import splice
from citesync.mapping import PEOPLE, TERMS, Mapping, load_mapping, person_terms, relative

# The @context of a codemeta.json write creates when codemeta-version is unset: the version
# the project template renders and Software Heritage reads.
NEW_CODEMETA_VERSION = "3.0"


def write(
    root: Path, config: Config, mapping: Mapping | None = None, *, dry_run: bool = False
) -> tuple[dict[str, str], dict[tuple[str, str], str], list[Finding], list[Finding]]:
    """Write every finding write may fix; return what it wrote and skipped, what it couldn't read, and what it fixed.

    It fixes the findings check reports, less those config ``ignore`` lists: in a derived
    citation file every term, in a manifest only the terms in ``write-manifests``, and only
    where the source holds the term and is what the file was compared with. A field the file
    leaves out stays out. An unreadable file is never written. A value the file's format can't
    spell without losing something is left as it was, its (path, term) mapped to the reason.
    Every new text is made before any file is replaced, so an error leaves the files as they were.
    With ``dry_run``, nothing is replaced.

    Returns:
        The new text of each path it changed, the reason for each (path, term) it left as it was, the
        ``unreadable`` findings, and the error findings it fixed.

    Raises:
        CheckError: as :func:`citesync.check.check` does, and when a file to write resolves outside ``root``.
    """
    mapping = mapping or load_mapping()
    docs, unreadable = read_docs(root, config, mapping)
    errors = [f for f in findings(docs, unreadable, config)[0] if f.severity == "error"]
    fix = {(f.file, f.term) for f in errors}
    source, texts, skipped, done = docs[0], {}, {}, set()
    key = keyword_key(config)
    for doc in docs:  # the source too, for its @context
        terms = [
            t
            for t in TERMS
            if (doc.path, t) in fix
            and has_slot(source, t)  # else the others were compared with each other (docs/check.md): left alone
            and t in source.record
            and t in doc.record
            and (doc.is_citation or t in config.write_manifests)
        ]
        context = config.codemeta_version if (doc.path, "@context") in fix else None
        if not terms and not context:
            continue
        old = (root / doc.path).read_bytes().decode("utf-8")  # bytes, so CRLF line ends stay
        lf = old.replace("\r\n", "\n")  # edited with LF line ends, which the YAML and JSON writers add
        new, reasons = _rewrite(doc, source, terms, lf, mapping, context, key)
        skipped |= {(doc.path, term): reason for term, reason in reasons.items()}
        if new != lf:
            crlf = old.count("\r\n") * 2 > old.count("\n")  # a file with both gets the more common one
            texts[doc.path] = new.replace("\n", "\r\n") if crlf else new
            changed = [*terms, "@context"] if context else terms
            done |= {(doc.path, t) for t in changed if t not in reasons}
    version = config.codemeta_version or NEW_CODEMETA_VERSION
    for rel in missing(root, config) if source.readable else ():
        if format_of(rel) == "codemeta" and (rel, None) in fix:
            texts[rel], reasons = _new_codemeta(rel, source, version, mapping, key)
            skipped |= {(rel, term): reason for term, reason in reasons.items()}
            done.add((rel, None))
    if not dry_run:
        for rel in texts:  # read_doc refuses an existing file outside; this catches a dangling link to one
            if not inside(root, rel):
                msg = f"{rel}: resolves outside the repo root, so write won't write it"
                raise CheckError(msg)
            (root / rel).parent.mkdir(parents=True, exist_ok=True)  # a listed docs/codemeta.json may be the first there
        _replace({root / rel: text for rel, text in texts.items()})
    fixed = [f for f in errors if (f.file, f.term) in done]
    return dict(sorted(texts.items())), skipped, [f for f in unreadable if f.rule == "unreadable"], fixed


def init(
    root: Path, config: Config, mapping: Mapping | None = None, *, dry_run: bool = False
) -> tuple[str, dict[str, str]]:
    """Write a new CITATION.cff from the files the repo has; return its text and the reason for each term left out.

    Each term comes from the first file that holds it: the configured source, then codemeta.json,
    .zenodo.json and the manifests in that order, so a citation file's ORCIDs and name parts win.
    With ``dry_run``, nothing is written.

    Raises:
        CheckError: when CITATION.cff exists, a file can't be read, or no file gives a title or authors.
    """
    if (root / "CITATION.cff").exists() or (root / "CITATION.cff").is_symlink():
        msg = "CITATION.cff already exists; `citesync write` makes it agree with another file"
        raise CheckError(msg)
    mapping = mapping or load_mapping()
    source = _merged(root, config, mapping)
    record = source.record
    cff = Doc("CITATION.cff", "cff-1.2.0", {}, frozenset(), "1.2.0", release=True)
    data = CommentedMap(
        [
            ("cff-version", "1.2.0"),
            ("message", "If you use this software, please cite it as below."),
            ("type", "software"),
        ]
    )
    blank = {  # the CFF key, and a blank whose shape picks the form, as in _new_codemeta
        "name": ("title", ""),
        "description": ("abstract", ""),
        "version": ("version", ""),
        "datePublished": ("date-released", dt.date.min),  # a date, so YAML writes it unquoted
        "author": ("authors", []),
        "identifier": ("doi", ""),
        "codeRepository": ("repository-code", ""),
        "license": ("license", ""),
        "keywords": ("keywords", []),
    }
    skipped = {}
    for term, (cff_key, old) in blank.items():
        if term not in record:
            continue
        try:
            if term in PEOPLE:
                data[cff_key] = _people(cff.format, old, source, str(mapping[cff.format, term]), mapping, term)
            else:
                data[cff_key] = _encode(cff, source, term, record[term], old, keyword_key(config))
        except CannotWrite as err:
            skipped[term] = str(err)
    yaml = YAML()
    yaml.width = 1 << 16
    yaml.indent(mapping=2, sequence=4, offset=2)
    out = io.StringIO()
    yaml.dump(data, out)
    if not dry_run:
        _replace({root / "CITATION.cff": out.getvalue()})
    return out.getvalue(), skipped


def _merged(root: Path, config: Config, mapping: Mapping) -> Doc:
    """The first file :func:`init` reads, holding each term from the first file that has it.

    Raises:
        CheckError: when there is no file to read, one can't be read, or none gives a title or authors.
    """
    first = next((p for p in (config.source, *CITATION_FILES, *MANIFESTS) if (root / p).is_file()), None)
    if first is None:
        msg = f"no codemeta.json, .zenodo.json or package manifest in {root} to make a CITATION.cff from"
        raise CheckError(msg)
    docs, read = read_docs(root, replace(config, source=first), mapping)
    if bad := next((f for f in read if f.rule == "unreadable"), None):
        msg = f"{bad.where}: {bad.message}"
        raise CheckError(msg)
    record: dict[str, Any] = {}
    for doc in docs:
        for term, value in doc.record.items():
            record.setdefault(term, value)
    for term, cff_key in (("name", "title"), ("author", "authors")):
        if term not in record:
            msg = f"no {cff_key} in {', '.join(d.path for d in docs)}, and CITATION.cff needs one"
            raise CheckError(msg)
    return replace(docs[0], record=record)


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
        head = re.match(r"(?:[ \t]*(?:#.*)?\n)*(?=---)", text)  # ruamel drops the comments above a ---
        return (head[0] if head else "") + out.getvalue(), skipped
    if doc.path.endswith(".toml"):
        data = tomlkit.parse(text)
        skipped = _apply(doc, source, terms, data, mapping, context, keyword_key)
        return tomlkit.dumps(data), skipped
    old = json.loads(text)
    data = copy.deepcopy(old)
    skipped = _apply(doc, source, terms, data, mapping, context, keyword_key)
    return splice(text, old, data), skipped


def _new_codemeta(
    rel: str, source: Doc, version: str, mapping: Mapping, keyword_key: Callable[[str], str]
) -> tuple[str, dict[str, str]]:
    """A codemeta.json at ``rel`` holding each term the source has, spelled as codemeta spells it.

    A term codemeta can't spell is left out, not left blank, and returned with the reason:
    a blank value reads as no value, so check would pass on it and write never fill it.
    """
    blank = {
        "name": "",
        "description": "",
        "version": "",
        "datePublished": "",
        "identifier": "https://doi.org/",  # the blanks' shapes pick the forms: DOI and SPDX URLs
        "codeRepository": "",
        "license": "https://spdx.org/licenses/",
        "author": [],
        "contributor": [],
        "keywords": [],
    }
    data: dict[str, Any] = {"@context": f"https://w3id.org/codemeta/{version}", "@type": "SoftwareSourceCode"}
    doc = Doc(rel, "codemeta", {}, frozenset(), version, release=True)
    skipped = {}
    for term in (t for t in blank if t in source.record):
        try:
            if term in PEOPLE:
                data[term] = _people("codemeta", blank[term], source, str(mapping["codemeta", term]), mapping, term)
            else:
                data[term] = _encode(doc, source, term, source.record[term], blank[term], keyword_key)
        except CannotWrite as err:
            skipped[term] = str(err)
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n", skipped


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
            skipped[term] = "inherited from [workspace.package] in the workspace's Cargo.toml"
            continue
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
    want, near_miss = set(map(key, value)), near_misses(value, key)
    for i, word in enumerate(items):  # a near miss takes the source's spelling where it stands
        if (near := near_miss(str(word))) and key(near) not in {key(str(k)) for k in items}:
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
    decoded = [person(fmt, el, path, mapping, term) for el in items]
    npm = term == "author" and "npm" in {fmt, source.format}
    people: tuple[Person, ...] = source.record[term][:1] if npm else source.record[term]
    matches = _matches(decoded, people)
    used = {i for i in matches if i is not None}
    if fmt == "zenodo" and term == "contributor" and None in matches:
        msg = "Zenodo needs a type for each contributor, which citesync doesn't choose"
        raise CannotWrite(msg)
    if mapping[fmt, f"{term}.@id"] is None and (
        nameless := next((p for p, i in zip(people, matches, strict=True) if i is None and not p.name), None)
    ):
        msg = f"{nameless.orcid} has no name, and this file has no place for an ORCID"
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
        if not same_name(q, p):
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
    by_name = (i for i, q in free if p.name and same_name(q, p))
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
    keys = {relative(str(mapping[fmt, t]), path) for t in person_terms(term)[:2]}
    if fmt == "cff-1.2.0" and cff_person(element).get("family-names") == fields.get("family-names"):
        keys.discard("family-names")  # only the given name changed: the particle and suffix stay as they are
    elif fmt == "cff-1.2.0":
        for key in ("name-particle", "name-suffix"):
            element.pop(key, None)  # folded into family-names by now
    for key in keys:
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

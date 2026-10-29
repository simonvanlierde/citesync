"""Rewrite the files that disagree with the source, changing only what check reports.

Each file is edited in a form that keeps the rest of it as it was: CFF through
ruamel.yaml's round trip (comments, key order, quoting), TOML through tomlkit
(comments, layout), and JSON by splicing each changed value into the original
text (key order, indentation, inline arrays, trailing newline). Values are
spelled the way the target format spells them, through :mod:`citesync.codecs`.
"""

import copy
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
from citesync.check import Finding, findings, has_slot, keyword_key, read_docs
from citesync.config import Config
from citesync.formats import MANIFESTS, Doc, Person, cff_person, codemeta_version, format_of, person, url_label
from citesync.mapping import PERSON_TERMS, TERMS, Mapping, load_mapping, relative, resolve


def write(root: Path, config: Config, mapping: Mapping | None = None) -> list[str]:
    """Write every finding write may fix, and return the paths it changed, sorted.

    It fixes the findings check reports, less those config ``ignore`` lists: in a derived
    citation file every term, in a manifest only the terms in ``write-manifests``, and only
    where the source holds the term and is what the file was compared with. A field the file
    leaves out stays out. An unreadable file is never written. Every new text is made before
    any file is replaced, so an error leaves the files as they were.

    Raises:
        CheckError: as :func:`citesync.check.check` does.
    """
    mapping = mapping or load_mapping()
    docs, unreadable = read_docs(root, config, mapping)
    fix = {(f.file, f.term) for f in findings(docs, unreadable, config) if f.rule not in config.ignore}
    source, texts = docs[0], {}
    key = keyword_key(case_sensitive=config.keywords_case_sensitive)
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
        new = _rewrite(doc, source, terms, old, mapping, context, key)
        if new != old:
            texts[doc.path] = new
    for rel, text in texts.items():
        _replace(root / rel, text)
    return sorted(texts)


def advice(finding: Finding, config: Config) -> str:
    """What to do about a finding write left: a manifest field it may not write can be opted in."""
    if (
        finding.file
        and finding.term
        and format_of(finding.file) in MANIFESTS.values()
        and finding.term not in config.write_manifests
    ):
        return f"edit it by hand, or add {finding.term} to write-manifests"
    return "edit it by hand"


def _replace(path: Path, text: str) -> None:
    """Write ``text`` to a temporary file beside ``path``, then move it over ``path``."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as file:
            file.write(text)
        shutil.copymode(path, tmp)
        Path(tmp).replace(path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _rewrite(
    doc: Doc,
    source: Doc,
    terms: list[str],
    text: str,
    mapping: Mapping,
    context: str | None,
    keyword_key: Callable[[str], str],
) -> str:
    if doc.format == "cff-1.2.0":
        yaml = _yaml(text)
        data = yaml.load(text)
        _apply(doc, source, terms, data, mapping, context, keyword_key)
        out = io.StringIO()
        yaml.dump(data, out)
        return out.getvalue()
    if doc.path.endswith(".toml"):
        data = tomlkit.parse(text)
        _apply(doc, source, terms, data, mapping, context, keyword_key)
        return tomlkit.dumps(data)
    old = json.loads(text)
    data = copy.deepcopy(old)
    _apply(doc, source, terms, data, mapping, context, keyword_key)
    return _splice(text, old, data)


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
) -> None:
    if context:
        iri = f"https://w3id.org/codemeta/{context}"
        old = data["@context"]
        data["@context"] = [iri if codemeta_version(c) else c for c in old] if isinstance(old, list) else iri
    if doc.format == "cargo" and "package" not in data:
        data = {"package": data["workspace"]["package"]}  # a virtual workspace, edited in place
    for term in terms:
        path = mapping[doc.format, term]
        assert path is not None  # noqa: S101 - write() only passes terms the file holds
        slot = _slot(term, data, path)
        if slot is None:
            continue
        container, key = slot
        old = container[key]
        if isinstance(old, dict) and old.get("workspace") is True:
            continue  # Cargo inherits it from [workspace.package]: edit it there by hand
        if term == "author":
            new = _people(doc.format, old, source, path, mapping)
        else:
            new = _encode(doc, source, term, source.record[term], old, keyword_key)
        if new is not old:
            _set(container, key, _styled(new, old), old)


def _slot(term: str, data: Any, path: str) -> tuple[Any, str] | None:  # noqa: ANN401
    """(container, key) of the value the reader reads at ``path``: the first alternative that has one."""
    for alternative in path.split(" | "):
        parent, _, key = alternative.rpartition(".")
        key = key.removesuffix("[]")
        for node in resolve(data, parent) if parent else [data]:
            if not isinstance(node, dict):
                continue
            # a PEP 621 url label reads as packaging normalises it, the exact label first
            label = key if key in node else next((k for k in node if url_label(k) == key), None)
            if label is None or (term == "codeRepository" and codecs.doi_decode(node[label])):
                continue  # Zenodo's isSupplementTo also lists papers by DOI
            return node, label
    return None


def _encode(doc: Doc, source: Doc, term: str, value: Any, old: Any, keyword_key: Callable[[str], str]) -> Any:  # noqa: ANN401, PLR0911
    """``value`` spelled for ``doc``'s format, in the shape ``old`` has; ``keyword_key`` compares keywords."""
    fmt = doc.format
    if term == "version":
        if fmt in {"cargo", "npm"}:
            return codecs.version_encode_semver(value)
        return str(codecs.version_key(value)) if fmt == "pep621" else value
    if term == "license":
        return _license(fmt, value, old)
    if term == "identifier":
        if isinstance(old, list):  # codemeta: the first DOI in the list is the one read
            i = next(i for i, el in enumerate(old) if codecs.doi_decode(el))
            return [*old[:i], _encode(doc, source, term, value, old[i], keyword_key), *old[i + 1 :]]
        form = "url" if isinstance(old, str) and old.strip().lower().startswith("http") else "bare"
        return codecs.doi_encode(value, form)
    if term == "codeRepository":
        if isinstance(old, dict):  # npm's {type, url}
            old["url"] = _encode(doc, source, term, value, old["url"], keyword_key)
            return old
        old = old.strip()
        return ("git+" if old.startswith("git+") else "") + value + (".git" if old.endswith(".git") else "")
    if term == "keywords":
        return _keywords(old, value, keyword_key, add=doc.is_citation, remove=source.is_citation or not doc.is_citation)
    return value


def _license(fmt: str, spdx: str, old: Any) -> Any:  # noqa: ANN401
    """CFF and codemeta write ``A OR B`` as a list, codemeta as SPDX URLs where the file does."""
    if fmt == "zenodo":
        return codecs.license_encode(spdx, "zenodo")
    if isinstance(old, dict) and "text" in old:  # PEP 621's legacy {text = ...}
        old["text"] = spdx
        return old
    if fmt not in {"cff-1.2.0", "codemeta"}:
        return spdx
    first = old[0] if isinstance(old, list) and old else old
    form = "spdx-url" if isinstance(first, str) and first.startswith("http") else "spdx"
    ids = [codecs.license_encode(i, form) for i in spdx.split(" OR ")]
    return ids if len(ids) > 1 or isinstance(old, list) else ids[0]


def _keywords(old: Any, value: tuple[str, ...], key: Callable[[str], str], *, add: bool, remove: bool) -> Any:  # noqa: ANN401
    """``old`` with the words not in ``value`` removed, and those missing added at the end, as the rule asks.

    Words compare by ``key``.

    Between citation files the sets must be equal (both); a manifest's must be a
    subset of a citation file's, so only the manifest loses words, or only the citation file gains them.
    """
    items = old if isinstance(old, list) else [old]
    want = set(map(key, value))
    if remove:
        for i in reversed(range(len(items))):
            if key(str(items[i])) not in want:
                del items[i]
    if add:
        have = {key(str(k)) for k in items}
        items.extend(_styled(k, items[0] if items else None) for k in value if key(k) not in have)
    return items


def _people(fmt: str, old: Any, source: Doc, path: str, mapping: Mapping) -> Any:  # noqa: ANN401
    """The author list for ``fmt``, with the source's people in the source's order.

    An existing entry is kept, with its other fields, when its name or ORCID
    matches; it is renamed on an ORCID match and gets the source's ORCID where
    both have one. Anyone else becomes a new entry, so an email or affiliation
    never moves to a different person. Entries with no name or ORCID stay, at the
    end. npm keeps one author, so only the first is set and the rest stay.
    """
    items = list(old) if isinstance(old, list) else [old]
    decoded = [_decode(fmt, el, path, mapping) for el in items]
    npm = "npm" in {fmt, source.format}
    people: tuple[Person, ...] = source.record["author"][:1] if npm else source.record["author"]
    used: set[int] = set()
    out = []
    for p in people:
        i = _match(decoded, used, p)
        if i is None:
            out.append(_new_person(fmt, p, path, mapping, items[0] if items else None))
            continue
        used.add(i)
        q = decoded[i]
        assert q is not None  # noqa: S101 - _match skips entries that read as no one
        if codecs.name_key(q.name or "") != codecs.name_key(p.name or ""):
            _rename(fmt, items[i], p, path, mapping)
        if q.orcid and p.orcid and q.orcid != p.orcid:
            okey = relative(str(mapping[fmt, "author.@id"]), path)
            items[i][okey] = _styled(_fields(fmt, p, path, mapping)[okey], items[i][okey])
        out.append(items[i])
    out += [el for i, el in enumerate(items) if i not in used and (npm or decoded[i] is None)]
    if not isinstance(old, list):
        return out[0] if len(out) == 1 or fmt == "npm" else out
    _relist(old, out)
    return old


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


def _decode(fmt: str, element: Any, path: str, mapping: Mapping) -> Person | None:  # noqa: ANN401
    if fmt == "cff-1.2.0" and isinstance(element, dict):
        element = cff_person(element)
    elif fmt == "npm" and isinstance(element, str):
        element = {"name": element}
    return person(fmt, element, path, mapping)


def _match(decoded: list[Person | None], used: set[int], p: Person) -> int | None:
    """The first unused entry with ``p``'s name, else the first with ``p``'s ORCID."""
    free = [(i, q) for i, q in enumerate(decoded) if q is not None and i not in used]
    by_name = (i for i, q in free if p.name and codecs.name_key(q.name or "") == codecs.name_key(p.name))
    by_orcid = (i for i, q in free if p.orcid and q.orcid == p.orcid)
    return next(by_name, next(by_orcid, None))


def _fields(fmt: str, p: Person, path: str, mapping: Mapping) -> dict[str, str]:
    """A person's name and ORCID under the keys ``fmt`` keeps them in."""
    gkey, fkey, okey = (relative(at, path) if (at := mapping[fmt, t]) else None for t in PERSON_TERMS)
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


def _new_person(fmt: str, p: Person, path: str, mapping: Mapping, like: Any) -> Any:  # noqa: ANN401
    fields = _fields(fmt, p, path, mapping)
    if fmt == "cargo" or (fmt == "npm" and not isinstance(like, dict)):
        return p.name or ""
    if fmt == "pep621":
        table = tomlkit.inline_table()
        table.update(fields)
        return table
    if fmt == "codemeta":
        return {"@type": "Person", **fields}
    if fmt == "cff-1.2.0":
        return CommentedMap((k, _styled(v, like.get(k) if isinstance(like, dict) else None)) for k, v in fields.items())
    return fields


def _rename(fmt: str, element: Any, p: Person, path: str, mapping: Mapping) -> None:  # noqa: ANN401
    """Set the name of an entry matched by ORCID, in place; only the citation files have ORCIDs."""
    fields = _fields(fmt, p, path, mapping)
    if fmt == "cff-1.2.0":
        for key in ("name-particle", "name-suffix"):
            element.pop(key, None)  # folded into family-names by now
    for key in {relative(str(mapping[fmt, t]), path) for t in PERSON_TERMS[:2]}:
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
    elif "\n" in text[start:end]:  # a multi-line value stays multi-line, at the indentation of its line
        line = text[text.rfind("\n", 0, start) + 1 :]
        margin = line[: len(line) - len(line.lstrip(" \t"))]
        edits.append((start, end, json.dumps(new, indent=indent, ensure_ascii=False).replace("\n", "\n" + margin)))
    else:
        edits.append((start, end, json.dumps(new, ensure_ascii=False)))

"""Compare the files' records term by term and report what disagrees."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path

from citesync import codecs
from citesync.config import Config
from citesync.errors import CheckError, UnreadableError
from citesync.formats import CITATION_FILES, MANIFESTS, Doc, Person, format_of, read_doc, slots
from citesync.mapping import FORMATS, TERMS, Mapping, load_mapping
from citesync.rules import DOCS_URL, MISMATCH, RULES


@dataclass(frozen=True)
class Finding:
    """One finding from a rule in :data:`citesync.rules.RULES`.

    ``file`` is None for a ``not-checked`` term no file holds, ``term`` None for an
    ``unreadable`` file. ``line`` and ``column`` are 1-based, when known.
    """

    file: str | None
    term: str | None
    rule: str
    message: str = field(compare=False)  # one finding per file, term and rule: the first comparison wins
    line: int | None = field(default=None, compare=False)
    column: int | None = field(default=None, compare=False)

    @property
    def severity(self) -> str:
        """``error``, ``warning`` or ``info``, from the rule."""
        return RULES[self.rule].severity

    def sort_key(self) -> tuple[bool, str, str, str]:
        """Findings sort by file, rule and term; those on no file come last."""
        return (self.file is None, self.file or "", self.rule, self.term or "")

    def as_dict(self) -> dict[str, str | int | None]:
        """The JSON form."""
        rule = RULES[self.rule]
        return {
            "rule": self.rule,
            "severity": rule.severity,
            "file": self.file,
            "term": self.term,
            "message": self.message,
            "help": rule.help,
            "url": f"{DOCS_URL}#{self.rule}",
            "line": self.line,
            "column": self.column,
        }


def discover(root: Path, config: Config) -> list[str]:
    """The files to compare, source first.

    Default: every citation file present, and every manifest at the root. A
    ``manifests`` list replaces the default list. A listed citation file that
    doesn't exist yet is skipped here; :func:`read_docs` reports it.

    Raises:
        CheckError: when the source or a listed manifest is missing.
    """
    if not (root / config.source).is_file():
        msg = f"{config.source}: the source file is missing"
        raise CheckError(msg)
    citation = config.files if config.files is not None else tuple(CITATION_FILES)
    paths = [config.source, *(p for p in citation if (root / p).is_file())]
    if config.manifests is None:
        paths += [p for p in MANIFESTS if (root / p).is_file()]
    else:
        for path in config.manifests:
            if not (root / path).is_file():
                msg = f"{path}: listed under manifests but missing"
                raise CheckError(msg)
        paths += config.manifests
    return list(dict.fromkeys(paths))


def missing(root: Path, config: Config) -> list[str]:
    """The citation files the ``files`` setting lists that don't exist."""
    return [p for p in config.files or () if not (root / p).is_file()]


def read_docs(root: Path, config: Config, mapping: Mapping) -> tuple[list[Doc], list[Finding]]:
    """Read the files to compare, leaving out root manifests that aren't released.

    The source comes first, then the others in a fixed order (citation files, then
    manifests, by format), so which file a finding names never depends on config order.
    A file that can't be read gives an ``unreadable`` finding and an empty doc in its place.
    """
    docs, unreadable = [], [Finding(p, None, "file-missing", "listed under files") for p in missing(root, config)]
    for path in discover(root, config):
        try:
            docs.append(read_doc(root, path, mapping))
        except UnreadableError as err:
            unreadable.append(Finding(err.path, None, "unreadable", err.message, err.line, err.column))
            fmt = format_of(path)
            docs.append(Doc(path, fmt, {}, slots(fmt, mapping), None, release=True, readable=False))
    if config.manifests is None:  # a manifest named in config, or the source, is checked whatever it is
        docs = [d for d in docs if d.release or d.is_citation or d.path == config.source]
    return docs[:1] + sorted(docs[1:], key=lambda d: (FORMATS.index(d.format), d.path)), unreadable


def check(root: Path, config: Config) -> tuple[list[Finding], int]:
    """Every finding for the repo at ``root``, sorted, and the number of files checked."""
    docs, unreadable = read_docs(root, config, load_mapping())
    return findings(docs, unreadable, config), len(docs)


def findings(docs: list[Doc], unreadable: list[Finding], config: Config) -> list[Finding]:
    """Every finding for ``docs`` (the source first) as :func:`read_docs` gives them, sorted."""
    found: set[Finding] = set(unreadable)
    source = docs[0]
    for doc in docs:
        if doc.readable and doc.format == "codemeta" and doc.version != config.codemeta_version:
            detail = f"{doc.version}, configured {config.codemeta_version}"
            found.add(Finding(doc.path, "@context", "context-mismatch", detail))
        for key in dict.fromkeys(key for key, _ in doc.dangling_roles):
            orcids = ", ".join(orcid for k, orcid in doc.dangling_roles if k == key)
            detail = f"a Role points at {orcids}, which no Person in author or contributor has"
            found.add(Finding(doc.path, key, "role-dangling", detail))
        for key, rule in doc.zenodo_gaps:
            found.add(Finding(doc.path, key, rule, _ZENODO_GAPS[rule]))
    for term in TERMS:
        if not source.readable and has_slot(source, term):
            found.add(Finding(source.path, term, "not-checked", "not compared with the source: it can't be read"))
        elif not any(term in d.record for d in docs):
            found.add(Finding(None, term, "not-checked", "no file holds a value"))
            continue
        found.update(compare_term(term, docs, kw_key=keyword_key(config)))
    return sorted(found, key=Finding.sort_key)


_ZENODO_GAPS = {
    "zenodo-license-list": "a list: with no .zenodo.json, Zenodo reads one licence and refuses the release",
    "zenodo-drops-field": "with no .zenodo.json, Zenodo leaves this out of the record",
}


def has_slot(doc: Doc, term: str) -> bool:
    """Whether ``doc`` can be the reference for ``term``: a manifest's name and description never are."""
    return term in doc.slots and (doc.is_citation or term not in {"name", "description"})


def compare_term(term: str, docs: list[Doc], *, kw_key: Callable[[str], str]) -> Iterable[Finding]:
    """Compare ``term`` in ``docs[1:]`` with the source ``docs[0]``.

    When the source has no slot or no value for it (D2), the other files that hold
    it are compared with each other. A source with no ORCID slot (a manifest) also
    gets its authors' ORCIDs compared that way, and a manifest source gets the
    keywords of the rest compared that way, since a subset of one isn't a subset of all.
    """
    source, others = docs[0], [d for d in docs[1:] if term in d.record]
    if has_slot(source, term) and term in source.record:
        found = [compare(term, source, doc, kw_key=kw_key) for doc in others]
        if term == "author" and "author.@id" not in source.slots:
            found += _between(term, others, orcid_only=True, kw_key=kw_key)
        elif term == "keywords" and not source.is_citation:
            found += _between(term, others, kw_key=kw_key)
    else:
        found = _between(term, others, kw_key=kw_key)
    return [f for f in found if f]


def _between(
    term: str, holders: list[Doc], *, orcid_only: bool = False, kw_key: Callable[[str], str]
) -> list[Finding | None]:
    return [
        compare(term, earlier, later, orcid_only=orcid_only, kw_key=kw_key)
        for i, later in enumerate(holders)
        for earlier in holders[:i]
    ]


def compare(term: str, ref: Doc, doc: Doc, *, orcid_only: bool = False, kw_key: Callable[[str], str]) -> Finding | None:
    """A finding on ``doc`` when its ``term`` disagrees with ``ref``'s, by the rule for that term and pair.

    With ``orcid_only``, authors compare by ORCID alone, for people whose names match. Keywords
    compare by ``kw_key`` (:func:`keyword_key`).
    """
    a, b = ref.record[term], doc.record[term]
    both_citation = ref.is_citation and doc.is_citation
    if term in _KEY:
        equal = a == b or _KEY[term](a) == _KEY[term](b)  # equal text needs no parsing (packaging costs 2.5 ms)
    elif term == "author":
        equal = _same_people(ref, doc, names=not orcid_only)
        a, b = _show_people(a), _show_people(b)
    elif term == "keywords":
        kw_key = cargo_keyword_key(kw_key, ref, doc)
        if not both_citation:
            return _keywords_subset(ref, doc, kw_key)
        equal = set(map(kw_key, a)) == set(map(kw_key, b))
    else:  # name, description
        if not both_citation:
            return None  # a manifest name is a package id, a description a one-line summary
        equal = a == b
    if equal:
        return None
    detail = f"{_show(b)}, {ref.path} has {_show(a)}"
    if term == "keywords":
        misses = [f"{k!r} differs from {near!r}" for k in b if (near := near_miss(k, a, kw_key))]
        detail += f" ({', '.join(misses)} only in separators)" if misses else ""
    return Finding(doc.path, term, MISMATCH[term], detail)


_KEY = {
    "version": codecs.version_key,
    "license": codecs.license_key,
    "identifier": codecs.doi_key,
    "codeRepository": codecs.repo_key,
}


def keyword_key(config: Config) -> Callable[[str], str]:
    """What keywords compare by: as names do, or with only the spacing collapsed when case-sensitive.

    With ``keywords-ignore-separators``, hyphens and underscores count as spaces too.
    """
    key = codecs.clean if config.keywords_case_sensitive else codecs.name_key
    return _ignore_separators(key) if config.keywords_ignore_separators else key


def cargo_keyword_key(key: Callable[[str], str], *docs: Doc) -> Callable[[str], str]:
    """``key``, ignoring separators when one of ``docs`` is a Cargo.toml: crates.io refuses a keyword with a space."""
    return _ignore_separators(key) if any(d.format == "cargo" for d in docs) else key


def _ignore_separators(key: Callable[[str], str]) -> Callable[[str], str]:
    return lambda k: key(codecs.spaced(k))


def near_miss(keyword: str, others: Iterable[str], key: Callable[[str], str]) -> str | None:
    """The one of ``others`` that ``keyword`` misses only by separators, when it isn't among them as it is."""
    if key(keyword) in map(key, others):
        return None
    return next((o for o in others if key(codecs.spaced(o)) == key(codecs.spaced(keyword))), None)


def _keywords_subset(ref: Doc, doc: Doc, key: Callable[[str], str]) -> Finding | None:
    """A manifest's keywords must all be in the citation file's, whichever is the source."""
    if not ref.is_citation and not doc.is_citation:
        return None  # no rule between two manifests
    manifest, citation = (ref, doc) if doc.is_citation else (doc, ref)
    known = set(map(key, citation.record["keywords"]))
    extra = [k for k in manifest.record["keywords"] if key(k) not in known]
    if not extra:
        return None
    words = [
        f"{k} ({citation.path} has {near!r}: differs only in separators)"
        if (near := near_miss(k, citation.record["keywords"], key))
        else k
        for k in extra
    ]
    detail = f"{', '.join(words)}: in {manifest.path}, not in {citation.path}"
    return Finding(doc.path, "keywords", "keywords-not-subset", detail)


def _same_people(ref: Doc, doc: Doc, *, names: bool) -> bool:
    """Same names in the same order, ORCIDs equal where both have one. npm's one author is the first.

    Without ``names``, only the ORCIDs of people at the same place with the same name count.
    """
    a: tuple[Person, ...] = ref.record["author"]
    b: tuple[Person, ...] = doc.record["author"]
    if "npm" in {ref.format, doc.format}:
        a, b = a[:1], b[:1]
    if names and len(a) != len(b):
        return False
    for p, q in zip(a, b, strict=False):
        same_name = codecs.name_key(p.name or "") == codecs.name_key(q.name or "")
        if names and not same_name:
            return False
        if same_name and p.orcid and q.orcid and p.orcid != q.orcid:
            return False
    return True


def _show_people(people: tuple[Person, ...]) -> str:
    return "; ".join(f"{p.name or '?'}" + (f" ({p.orcid})" if p.orcid else "") for p in people)


def _show(value: object) -> str:
    if isinstance(value, tuple):
        return ", ".join(map(str, value))
    text = str(value)
    return repr(text if len(text) <= 80 else text[:77] + "...")

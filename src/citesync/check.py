"""Compare the files' records term by term and report what disagrees."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from citesync import codecs
from citesync.config import Config
from citesync.errors import CheckError
from citesync.formats import CITATION_FILES, MANIFESTS, Doc, Person, read_doc
from citesync.mapping import TERMS, Mapping, load_mapping


@dataclass(frozen=True, order=True)
class Finding:
    """One disagreement, or with ``NOT_CHECKED`` a term no file holds. Sorted by file, term and code."""

    file: str
    term: str
    code: str
    detail: str = field(compare=False)

    def __str__(self) -> str:
        where = f"{self.file}: " if self.file else ""
        return f"{self.code} {where}{self.term}: {self.detail}"

    def as_dict(self) -> dict[str, str]:
        """The JSON form."""
        return {"code": self.code, "file": self.file, "term": self.term, "detail": self.detail}


def discover(root: Path, config: Config) -> list[str]:
    """The files to compare, source first.

    Default: every citation file present, and every manifest at the root. A
    ``manifests`` list replaces the default list. A listed citation file that
    doesn't exist yet is skipped: there is nothing to compare until write makes it.

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


def read_docs(root: Path, config: Config, mapping: Mapping) -> list[Doc]:
    """Read the files to compare, source first, leaving out root manifests that aren't released."""
    docs = []
    for path in discover(root, config):
        try:
            docs.append(read_doc(root, path, mapping))
        except (AttributeError, TypeError) as err:  # a key holding a shape its format doesn't allow
            msg = f"{path}: cannot read: unexpected shape ({err})"
            raise CheckError(msg) from err
    if config.manifests is None:  # a manifest named in config, or the source, is checked whatever it is
        docs = [d for d in docs if d.release or d.is_citation or d.path == config.source]
    return docs


def check(root: Path, config: Config, mapping: Mapping | None = None) -> tuple[list[Finding], list[Finding]]:
    """Findings and ``NOT_CHECKED`` info for the repo at ``root``, each sorted."""
    docs = read_docs(root, config, mapping or load_mapping())
    findings: set[Finding] = set()
    info = []
    for doc in docs:
        if doc.format == "codemeta" and doc.version != config.codemeta_version:
            findings.add(
                Finding(doc.path, "@context", "CONTEXT", f"{doc.version}, configured {config.codemeta_version}")
            )
    for term in TERMS:
        if not any(term in d.record for d in docs):
            info.append(Finding("", term, "NOT_CHECKED", "no file holds a value"))
            continue
        findings.update(compare_term(term, docs))
    return sorted(findings), sorted(info)


def has_slot(doc: Doc, term: str) -> bool:
    """Whether ``doc`` can be the reference for ``term``: a manifest's name and description never are."""
    return term in doc.slots and (doc.is_citation or term not in {"name", "description"})


def compare_term(term: str, docs: list[Doc]) -> Iterable[Finding]:
    """Compare ``term`` in ``docs[1:]`` with the source ``docs[0]``.

    When the source has no slot or no value for it (D2), the other files that hold
    it are compared with each other. A source with no ORCID slot (a manifest) also
    gets its authors' ORCIDs compared that way.
    """
    source, others = docs[0], [d for d in docs[1:] if term in d.record]
    if has_slot(source, term) and term in source.record:
        found = [compare(term, source, doc) for doc in others]
        if term == "author" and "author.@id" not in source.slots:
            found += _between(term, others)
    else:
        found = _between(term, others)
    return [f for f in found if f]


def _between(term: str, holders: list[Doc]) -> list[Finding | None]:
    return [compare(term, earlier, later) for i, later in enumerate(holders) for earlier in holders[:i]]


def compare(term: str, ref: Doc, doc: Doc) -> Finding | None:
    """A finding on ``doc`` when its ``term`` disagrees with ``ref``'s, by the rule for that term and pair."""
    a, b = ref.record[term], doc.record[term]
    both_citation = ref.is_citation and doc.is_citation
    if term in {"name", "description"}:
        if not both_citation:
            return None  # a manifest name is a package id, a description a one-line summary
        equal = a == b
    elif term == "version":
        equal = codecs.version_key(a) == codecs.version_key(b)
    elif term == "license":
        equal = codecs.license_key(a) == codecs.license_key(b)
    elif term == "identifier":
        equal = codecs.doi_key(a) == codecs.doi_key(b)
    elif term == "author":
        equal = _same_people(ref, doc)
        a, b = _show_people(a), _show_people(b)
    elif term == "keywords":
        if not both_citation:
            return _keywords_subset(ref, doc)
        equal = set(a) == set(b)
    else:
        equal = a == b
    if equal:
        return None
    return Finding(doc.path, term, "MISMATCH", f"{_show(b)}, {ref.path} has {_show(a)}")


def _keywords_subset(ref: Doc, doc: Doc) -> Finding | None:
    """A manifest's keywords must all be in the citation file's, whichever is the source."""
    if not ref.is_citation and not doc.is_citation:
        return None  # no rule between two manifests
    manifest, citation = (ref, doc) if doc.is_citation else (doc, ref)
    extra = [k for k in manifest.record["keywords"] if k not in set(citation.record["keywords"])]
    if not extra:
        return None
    detail = f"{', '.join(extra)}: in {manifest.path}, not in {citation.path}"
    return Finding(doc.path, "keywords", "NOT_SUBSET", detail)


def _same_people(ref: Doc, doc: Doc) -> bool:
    """Same names in the same order, ORCIDs equal where both have one. npm's one author is the first."""
    a: tuple[Person, ...] = ref.record["author"]
    b: tuple[Person, ...] = doc.record["author"]
    if "npm" in {ref.format, doc.format}:
        a, b = a[:1], b[:1]
    if len(a) != len(b):
        return False
    for p, q in zip(a, b, strict=True):
        if codecs.name_key(p.name or "") != codecs.name_key(q.name or ""):
            return False
        if p.orcid and q.orcid and p.orcid != q.orcid:
            return False
    return True


def _show_people(people: tuple[Person, ...]) -> str:
    return "; ".join(f"{p.name or '?'}" + (f" ({p.orcid})" if p.orcid else "") for p in people)


def _show(value: object) -> str:
    if isinstance(value, tuple):
        return ", ".join(map(str, value))
    text = str(value)
    return repr(text if len(text) <= 80 else text[:77] + "...")

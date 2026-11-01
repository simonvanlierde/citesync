"""Browser generation adapter; each request uses an isolated, temporary repository."""

import base64
import io
import json
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from citesync.check import check, keyword_key
from citesync.config import Config
from citesync.errors import CheckError
from citesync.formats import FORMAT_OF, Doc, load, read_doc
from citesync.formats import person as read_person
from citesync.mapping import Mapping, load_mapping
from citesync.playground_exports import bibliography, package_templates
from citesync.write import NEW_CODEMETA_VERSION, _new_codemeta, _split_name, init, write

_FORM_FIELDS = (
    ("title", "name"),
    ("description", "description"),
    ("version", "version"),
    ("license", "license"),
    ("repository", "codeRepository"),
)


def generate(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate previews with the installed engine, without touching a user's repo.

    ``details`` contains a title, optional description/version/licence/repository and
    structured authors. Otherwise ``filename`` and ``text`` supply one supported file.
    ``names`` optionally corrects inferred given/family names in their displayed order.
    ``archive=True`` adds a citation ZIP on request. Input configuration is not loaded.
    ``edit=True`` returns form values retaining CodeMeta metadata. ``draft=True``
    serializes partial details without generating exports. Errors propagate as ``CheckError``.
    """
    with tempfile.TemporaryDirectory(prefix="citesync-preview-") as directory:
        return _generate(Path(directory), payload)


def _generate(root: Path, payload: dict[str, Any]) -> dict[str, Any]:
    filename = payload.get("filename", "codemeta.json")
    text = payload.get("text", "")
    if "details" in payload:
        filename, text = "codemeta.json", _details(payload["details"], draft=bool(payload.get("draft")))
    if filename not in FORMAT_OF:
        msg = "Choose CITATION.cff, codemeta.json, .zenodo.json, pyproject.toml, Cargo.toml or package.json."
        raise CheckError(msg)
    if not isinstance(text, str) or len(text.encode("utf-8")) > 1_000_000:
        msg = "Use a metadata file smaller than 1 MB."
        raise CheckError(msg)
    if "details" in payload and payload.get("draft"):
        return {"draft": text}
    (root / filename).write_text(text, encoding="utf-8", newline="")
    mapping = load_mapping()
    source = read_doc(root, filename, mapping)
    if not source.record.get("name") or not any(p.name for p in source.record.get("author", ())):
        if payload.get("edit"):
            return _partial_details(source, text, mapping)
        msg = "Add a software title and at least one author."
        raise CheckError(msg)
    if filename == "CITATION.cff":
        skipped, splits = {}, []
    else:
        _, skipped, splits = init(root, Config(source=filename, manifests=()), mapping)
    review = [{"original": name, "given": given, "family": family} for name, given, family in splits]
    if "names" in payload:
        _correct_names(root, payload["names"], splits, source.record["author"])
    config = Config(files=("codemeta.json", ".zenodo.json"), manifests=())
    _, omitted, unreadable, _ = write(root, config, mapping)
    if unreadable:
        raise CheckError(unreadable[0].message)
    files = {
        name: (root / name).read_bytes().decode("utf-8")
        for name in ("CITATION.cff", "codemeta.json", ".zenodo.json")
        if (root / name).is_file()
    }
    findings, _, _ = check(root, Config(files=tuple(n for n in files if n != "CITATION.cff"), manifests=()))
    notes = [f"CITATION.cff: {term}: {reason}" for term, reason in sorted(skipped.items())]
    notes += [f"{name}: {term}: {reason}" for (name, term), reason in sorted(omitted.items())]
    record = source.record | read_doc(root, "CITATION.cff", mapping).record
    citations, citation_notes = bibliography(record)
    templates, template_notes = package_templates(record)
    files.update(citations)
    return {
        "files": files,
        **({"details": _form_details(record, json.loads(files["codemeta.json"]))} if payload.get("edit") else {}),
        "review": review,
        "notes": notes + citation_notes,
        "findings": [f.as_dict() for f in findings],
        **({"zip": _archive(files)} if payload.get("archive") else {}),
        "templates": templates,
        "template_notes": template_notes,
    }


def _archive(files: dict[str, str]) -> str:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            bundle.writestr(name, content)
    return base64.b64encode(archive.getvalue()).decode("ascii")


def _details(details: dict[str, Any], *, draft: bool = False) -> str:
    if not draft and any(not author.get("family", "").strip() for author in details.get("authors", [])):
        msg = "Add a family name for each author to see your files."
        raise CheckError(msg)
    data: dict[str, Any] = dict(details.get("document", {}))
    data.setdefault("@context", "https://w3id.org/codemeta/3.0")
    data.setdefault("@type", "SoftwareSourceCode")
    for field, term in _FORM_FIELDS:
        if value := details.get(field, "").strip():
            data[term] = value
        else:
            data.pop(term, None)
    original = data.get("author", [])
    if not isinstance(original, list):
        original = [original]
    roles = [node for node in original if isinstance(node, dict) and node.get("@type", node.get("type")) == "Role"]
    authors = []
    for author in details.get("authors", []):
        node = dict(author.get("metadata", {}))
        for key in ("name", "givenName", "familyName", "@type", "type"):
            node.pop(key, None)
        if author.get("organization"):
            node.update({"@type": "Organization", "name": author.get("family", "").strip()})
        else:
            node["@type"] = "Person"
            node.update(
                {
                    key: author[field].strip()
                    for field, key in (("given", "givenName"), ("family", "familyName"))
                    if author.get(field, "").strip()
                }
            )
        authors.append(node)
    data["author"] = authors + roles
    return json.dumps(data, ensure_ascii=False, indent=2)


def _partial_details(source: Doc, text: str, mapping: Mapping) -> dict[str, Any]:
    document = (
        text
        if source.format == "codemeta"
        else _new_codemeta("codemeta.json", source, NEW_CODEMETA_VERSION, mapping, keyword_key(Config()))[0]
    )
    return {"details": _form_details(source.record, json.loads(document))}


def _form_details(record: dict[str, Any], document: dict[str, Any]) -> dict[str, Any]:
    """Project form values plus their original metadata for edits that retain extra fields."""
    fields = {key: record.get(term, "") for key, term in _FORM_FIELDS}
    raw = document.get("author", [])
    if not isinstance(raw, list):
        raw = [raw]
    mapping = load_mapping()
    metadata = [
        node if isinstance(node, dict) else {}
        for node in raw
        if read_person("codemeta", node, "author[]", mapping, "author") is not None
    ]
    authors = []
    for p, node in zip(record.get("author", ()), metadata, strict=True):
        given, family = (p.given or "", p.family or p.name or "")
        if p.family is None and not p.organization:
            given, family = _split_name(p.name)
        authors.append({"given": given, "family": family, "organization": p.organization, "metadata": node})
    fields["authors"] = authors
    fields["document"] = document
    return fields


def _correct_names(
    root: Path, names: list[dict[str, str]], splits: list[tuple[str, str, str]], people: list[Any]
) -> None:
    if len(names) != len(splits) or any(not n.get("family", "").strip() for n in names):
        msg = "Give each reviewed author a family name, or use structured citation metadata for organisations."
        raise CheckError(msg)
    data = load(root / "CITATION.cff", "CITATION.cff")
    corrections = iter(names)
    for author, person in zip(data["authors"], people, strict=True):
        if person.family is None and any(person.name == name for name, _, _ in splits):
            corrected = next(corrections)
            author["given-names"] = corrected["given"].strip()
            author["family-names"] = corrected["family"].strip()
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    with (root / "CITATION.cff").open("w", encoding="utf-8") as stream:
        yaml.dump(data, stream)

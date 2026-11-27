"""Project a static Maven POM into the fields named by the vendored mapping."""

from collections.abc import Mapping as ReadMapping
from typing import Any
from xml.etree import ElementTree as ET
from xml.parsers import expat

from citesync.errors import UnreadableError
from citesync.mapping import Mapping, _parse

_DOCTYPE_ERROR = "Maven POMs must not contain a document type declaration"
_PROJECT_NAMESPACES = {"", "http://maven.apache.org/POM/4.0.0", "http://maven.apache.org/POM/4.1.0"}


class _POMBuilder(ET.TreeBuilder):
    def doctype(self, _name: str, _pubid: str | None, _system: str | None) -> None:
        raise ValueError(_DOCTYPE_ERROR)


def parse(text: str, rel: str, mapping: Mapping) -> dict[str, Any]:
    """Read only the supplied POM, with no entity declarations or Maven model resolution."""
    try:
        root = ET.fromstring(text, parser=ET.XMLParser(target=_POMBuilder()))  # noqa: S314 - rejects DTDs
    except ET.ParseError as err:
        line, column = err.position
        raise UnreadableError(rel, str(err).split(": line ", 1)[0], line, column + 1) from err
    except ValueError as err:
        raise UnreadableError(rel, str(err)) from err

    namespace, _, tag = root.tag.rpartition("}")
    if tag != "project" or namespace.removeprefix("{") not in _PROJECT_NAMESPACES:
        raise UnreadableError(rel, "expected a Maven project element")
    prefix = f"{namespace}}}" if namespace else ""
    return _project(root, (), prefix, _mapped_children(mapping))


def _mapped_children(mapping: Mapping) -> dict[tuple[str, ...], dict[str, bool]]:
    # Only descend into mapped elements. A singleton developer is still a list.
    children: dict[tuple[str, ...], dict[str, bool]] = {}
    for (fmt, _), path in mapping.items():
        if fmt == "maven" and path:
            for parts in _parse(path):
                for steps in parts:
                    parent: tuple[str, ...] = ()
                    for key, _, _, many in steps:
                        children.setdefault(parent, {})[key] = many
                        parent = (*parent, key)
    return children


def key_positions(text: str, mapping: Mapping) -> dict[tuple[str, ...], tuple[int, int]]:
    """Find mapped Maven start tags for diagnostics, skipping other namespaces and subtrees."""
    children = _mapped_children(mapping)
    keys: dict[tuple[str, ...], tuple[int, int]] = {}
    parents: list[tuple[str, ...] | None] = []
    namespace = ""
    parser = expat.ParserCreate(namespace_separator="}")

    def start(tag: str, _attrs: dict[str, str]) -> None:
        nonlocal namespace
        ns, _, name = tag.rpartition("}")
        if not parents:
            namespace = ns
            parents.append(() if name == "project" and ns in _PROJECT_NAMESPACES else None)
            return
        parent = parents[-1]
        if parent is None or ns != namespace or name not in children.get(parent, {}):
            parents.append(None)
            return
        key = (*parent, name)
        keys.setdefault(key, (parser.CurrentLineNumber, parser.CurrentColumnNumber + 1))
        parents.append(key)

    def end(_tag: str) -> None:
        parents.pop()

    def reject_doctype(_name: str, _system: str | None, _public: str | None, _internal: int) -> None:
        raise ValueError(_DOCTYPE_ERROR)

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    parser.StartDoctypeDeclHandler = reject_doctype
    try:
        parser.Parse(text, True)  # noqa: FBT003 - this is the final chunk
    except (expat.ExpatError, ValueError):
        return {}
    return keys


def _project(
    node: ET.Element, path: tuple[str, ...], prefix: str, children: ReadMapping[tuple[str, ...], dict[str, bool]]
) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for key, many in children.get(path, {}).items():
        if not (elements := node.findall(prefix + key)):
            continue
        child_path = (*path, key)
        entries: list[Any]
        if child_path in children:
            entries = [_project(element, child_path, prefix, children) for element in elements]
        else:
            entries = [(element.text or "").strip() for element in elements]
        values[key] = entries if many else entries[0]
    return values

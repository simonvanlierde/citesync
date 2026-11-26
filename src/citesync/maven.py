"""Project a static Maven POM into the fields named by the vendored mapping."""

from collections.abc import Mapping as ReadMapping
from typing import Any
from xml.etree import ElementTree as ET

from citesync.errors import UnreadableError
from citesync.mapping import Mapping, _parse


class _POMBuilder(ET.TreeBuilder):
    def doctype(self, _name: str, _pubid: str | None, _system: str | None) -> None:
        msg = "Maven POMs must not contain a document type declaration"
        raise ValueError(msg)


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
    if tag != "project" or namespace not in {
        "",
        "{http://maven.apache.org/POM/4.0.0",
        "{http://maven.apache.org/POM/4.1.0",
    }:
        raise UnreadableError(rel, "expected a Maven project element")
    prefix = f"{namespace}}}" if namespace else ""

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
    return _project(root, (), prefix, children)


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

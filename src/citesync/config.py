"""Find and validate the config: the first location found wins, flags override it."""

import json
import tomllib
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any

from citesync.errors import CheckError
from citesync.formats import CITATION_FILES, CODEMETA_VERSIONS, FORMAT_OF, MANIFESTS
from citesync.mapping import TERMS

KEYS = ("source", "codemeta_version", "files", "manifests", "write_manifests", "keywords_case_sensitive")


@dataclass(frozen=True)
class Config:
    """The settings a check runs with. ``None`` for files or manifests means the default discovery."""

    source: str = "CITATION.cff"
    codemeta_version: str = "3.0"
    files: tuple[str, ...] | None = None
    manifests: tuple[str, ...] | None = None
    write_manifests: tuple[str, ...] = ()
    keywords_case_sensitive: bool = False
    origin: str = "defaults"


def find_config(root: Path) -> tuple[dict[str, Any], str]:
    """The raw config table and where it came from, in the D7 order; ``({}, "defaults")`` when none."""
    for name in ("citesync.toml", ".citesync.toml"):
        if (root / name).is_file():
            return _read(root, name), name
    if (root / "pyproject.toml").is_file():
        table = _dig(_read(root, "pyproject.toml"), ("tool", "citesync"), "pyproject.toml")
        if table is not None:
            return table, "pyproject.toml [tool.citesync]"
    if (root / "Cargo.toml").is_file():
        cargo = _read(root, "Cargo.toml")
        for section in ("workspace", "package"):
            table = _dig(cargo, (section, "metadata", "citesync"), "Cargo.toml")
            if table is not None:
                return table, f"Cargo.toml [{section}.metadata.citesync]"
    if (root / "package.json").is_file():
        table = _read(root, "package.json").get("citesync")
        if table is not None:
            return table, 'package.json "citesync"'
    return {}, "defaults"


def _dig(data: dict[str, Any], keys: tuple[str, ...], name: str) -> Any:  # noqa: ANN401 - parsed TOML
    """The value at ``keys`` in nested tables, or None when a key is missing."""
    node: Any = data
    for i, key in enumerate(keys):
        if not isinstance(node, dict):
            msg = f"{name}: {'.'.join(keys[:i])} is not a table"
            raise CheckError(msg)
        node = node.get(key)
        if node is None:
            return None
    return node


def _read(root: Path, name: str) -> dict[str, Any]:
    try:
        text = (root / name).read_text(encoding="utf-8")
        data = json.loads(text) if name.endswith(".json") else tomllib.loads(text)
    except (OSError, ValueError) as err:  # TOMLDecodeError and JSONDecodeError are ValueErrors
        msg = f"{name}: cannot read config: {err}"
        raise CheckError(msg) from err
    if not isinstance(data, dict):
        msg = f"{name}: the top level is not a table"
        raise CheckError(msg)
    return data


def load_config(root: Path, source: str | None = None) -> Config:
    """The config in use under ``root``, with ``source`` from the command line on top.

    Raises:
        CheckError: on an unknown key or a value citesync can't use.
    """
    raw, origin = find_config(root)
    if not isinstance(raw, dict):
        msg = f"{origin}: the citesync config is not a table"
        raise CheckError(msg)
    unknown = sorted(set(raw) - set(KEYS))
    if unknown:
        msg = f"{origin}: unknown key {', '.join(unknown)}; known keys: {', '.join(KEYS)}"
        raise CheckError(msg)
    config = Config(origin=origin)
    if "source" in raw:
        config = replace(config, source=_path(raw["source"], FORMAT_OF, origin, "source"))
    if source is not None:
        config = replace(config, source=_path(source, FORMAT_OF, "--source", "source"))
    if "codemeta_version" in raw:
        config = replace(config, codemeta_version=_codemeta_version(raw["codemeta_version"], origin))
    if "files" in raw:
        config = replace(config, files=_paths(raw["files"], CITATION_FILES, origin, "files"))
    if "manifests" in raw:
        config = replace(config, manifests=_paths(raw["manifests"], MANIFESTS, origin, "manifests"))
    if "write_manifests" in raw:
        config = replace(config, write_manifests=_write_manifests(raw["write_manifests"], origin))
    if "keywords_case_sensitive" in raw:
        config = replace(
            config, keywords_case_sensitive=_bool(raw["keywords_case_sensitive"], origin, "keywords_case_sensitive")
        )
    return config


def _codemeta_version(value: object, origin: str) -> str:
    if value not in CODEMETA_VERSIONS:
        msg = f"{origin}: codemeta_version must be one of {', '.join(CODEMETA_VERSIONS)}"
        raise CheckError(msg)
    return str(value)


def _bool(value: object, origin: str, key: str) -> bool:
    if not isinstance(value, bool):
        msg = f"{origin}: {key} must be true or false"
        raise CheckError(msg)
    return value


def _path(value: object, names: dict[str, str], origin: str, key: str) -> str:
    if not isinstance(value, str) or PurePosixPath(value).name not in names:
        msg = f"{origin}: {key} must name one of {', '.join(names)}, got {value!r}"
        raise CheckError(msg)
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        msg = f"{origin}: {key} {value!r} must be relative to the repo root, inside it"
        raise CheckError(msg)
    return str(path)


def _paths(value: object, names: dict[str, str], origin: str, key: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        msg = f"{origin}: {key} must be a list of paths"
        raise CheckError(msg)
    return tuple(_path(item, names, origin, key) for item in value)


def _write_manifests(value: object, origin: str) -> tuple[str, ...]:
    items = [value] if isinstance(value, str) else value
    if not isinstance(items, list) or not all(isinstance(i, str) and (i in TERMS or i == "all") for i in items):
        msg = f"{origin}: write_manifests must be 'all' or a list of {', '.join(TERMS)}, got {value!r}"
        raise CheckError(msg)
    return tuple(TERMS) if "all" in items else tuple(items)


def render(config: Config) -> str:
    """The config as TOML, headed by where it came from (``citesync config``)."""
    lines = [
        f"# from {config.origin}",
        f"source = {json.dumps(config.source)}",
        f"codemeta_version = {json.dumps(config.codemeta_version)}",
        f"files = {json.dumps(list(config.files))}"
        if config.files is not None
        else "# files: not set, so every citation file present",
        f"manifests = {json.dumps(list(config.manifests))}"
        if config.manifests is not None
        else "# manifests: not set, so every release manifest at the repo root",
        f"write_manifests = {json.dumps(list(config.write_manifests))}",
        f"keywords_case_sensitive = {json.dumps(config.keywords_case_sensitive)}",
    ]
    return "\n".join(lines)

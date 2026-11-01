"""The hook in .pre-commit-hooks.yaml runs when any file citesync reads or exports may change, and only then."""

import re
from pathlib import Path

import pytest
from ruamel.yaml import YAML

from citesync.export import DEFAULT_NAMES
from citesync.formats import CITATION_FILES, IMPORTS, MANIFESTS

HOOK = YAML(typ="safe").load(Path(__file__).parent.parent / ".pre-commit-hooks.yaml")[0]
# an export may have any name with its suffix, such as docs/lensgrind.bib
NAMES = [
    *CITATION_FILES,
    *MANIFESTS,
    *IMPORTS,
    "citesync.toml",
    ".citesync.toml",
    *DEFAULT_NAMES.values(),
    "lensgrind.bib",
]


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("folder", ["", "src/core/"])
def test_files_pattern_matches_at_any_depth(name: str, folder: str) -> None:
    assert re.search(HOOK["files"], folder + name)


@pytest.mark.parametrize("path", ["README.md", "xCITATION.cff", "package.json.bak", "uv.lock", "citation.bib.bak"])
def test_files_pattern_skips_other_files(path: str) -> None:
    assert not re.search(HOOK["files"], path)


def test_write_hook_runs_only_when_asked() -> None:
    check, write = YAML(typ="safe").load(Path(__file__).parent.parent / ".pre-commit-hooks.yaml")
    assert (write["entry"], write["stages"], write["files"]) == ("citesync write", ["manual"], check["files"])

"""The website renders the repository's guides without duplicating their source."""

# ruff: noqa: SLF001 - test the build's publication boundary directly

import importlib.util
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("site_build", ROOT / "playground/build.py")
assert spec
assert spec.loader
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Links(HTMLParser):
    def __init__(self, text: str):
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if ident := values.get("id"):
            self.ids.add(ident)
        if tag in {"a", "link", "img", "script"} and (target := values.get("href") or values.get("src")):
            self.links.append(target)


def test_site_build_includes_docs_and_rewrites_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "repo"
    output = root / "playground"
    output.mkdir(parents=True)
    for name in (
        "style.css",
        "main.mjs",
        "detect.mjs",
        "picker.mjs",
        "lookup.mjs",
        "worker.mjs",
        "runtime.json",
        "lookup.json",
        "favicon.svg",
        "og.png",
    ):
        (output / name).write_text("asset")
    (output / "index.html").write_text(
        '<link href="style.css"><script src="main.mjs"></script>'
        '<a href="https://simonvanlierde.com/citesync/docs/">Documentation</a>'
    )
    wheels = output / "wheels"
    wheels.mkdir()
    (root / "docs").mkdir()
    (root / "docs/README.md").write_text("# Documentation\n\n[Guide](guide.md#same-heading)\n")
    (root / "docs/guide.md").write_text(
        "# Guide\n\n## Same heading\n\n## Same heading\n\n## Same heading-1\n\n"
        "[Source](../README.md#setup)\n\n```sh\n<not-markup>\n```\n"
    )
    (root / "README.md").write_text("# Repository\n\n## Setup\n")
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "OUTPUT", output)
    monkeypatch.setattr(builder, "WHEELS", wheels)
    builder._site({"version": "0.5.0", "wheels": []})
    assert 'href="docs/"' in (root / "site/index.html").read_text()
    landing = (root / "site/docs/index.html").read_text()
    guide = (root / "site/docs/guide/index.html").read_text()
    assert 'href="guide/#same-heading"' in landing
    assert 'id="same-heading"' in guide
    assert 'id="same-heading-1"' in guide
    assert 'id="same-heading-1-1"' in guide
    assert 'href="https://github.com/simonvanlierde/citesync/blob/main/README.md#setup"' in guide
    assert "&lt;not-markup&gt;" in guide
    assert "<not-markup>" not in guide
    assert 'href="../../"' in guide


def test_all_documentation_links_and_anchors_resolve(tmp_path: Path):
    (tmp_path / "index.html").write_text((ROOT / "playground/index.html").read_text())
    builder._docs(tmp_path, "assets/test")
    pages = {path: Links(path.read_text()) for path in (tmp_path / "docs").rglob("*.html")}
    expected = {path.relative_to(ROOT / "docs") for path in (ROOT / "docs").rglob("*.md")}
    assert len(pages) == len(expected)
    for path, parsed in pages.items():
        for link in parsed.links:
            url = urlsplit(link)
            if url.scheme or url.netloc or "assets/" in url.path or "favicon.svg" in url.path:
                continue
            target = (path.parent / unquote(url.path)).resolve()
            if target.is_dir():
                target /= "index.html"
            assert target.is_file(), (path, link)
            if url.fragment:
                assert unquote(url.fragment) in Links(target.read_text()).ids, (path, link)


def test_missing_documentation_link_stops_the_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/README.md").write_text("# Documentation\n\n[Missing guide](missing.md)\n")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(ValueError, match=r"linked file does not exist: missing\.md"):
        builder._docs(tmp_path / "site", "assets/test")

"""The website renders the repository's guides without duplicating their source."""

# ruff: noqa: SLF001 - test the build's publication boundary directly

import importlib.util
import json
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
        self.description: str | None = None
        self.meta: dict[str, str | None] = {}
        self.canonical: str | None = None
        self.feed(text)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "meta" and (key := values.get("property") or values.get("name")):
            self.meta[key] = values.get("content")
        if tag == "link" and values.get("rel") == "canonical":
            self.canonical = values.get("href")
        if tag == "meta" and values.get("name") == "description":
            self.description = values.get("content")
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
        "docs-search.mjs",
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
        '<a href="https://simonvanlierde.com/citesync/docs/accessibility/">Accessibility</a>'
    )
    wheels = output / "wheels"
    wheels.mkdir()
    (root / "docs").mkdir()
    (root / "docs/README.md").write_text("# Documentation\n\n[Guide](guide.md#same-heading)\n")
    (root / "docs/guide.md").write_text(
        "# Guide\n\n## Same heading\n\n## Same heading\n\n## Same heading-1\n\n"
        "[Source](../README.md#setup)\n\n"
        "[Guide copied from GitHub](https://github.com/simonvanlierde/citesync/blob/main/README.md#setup)\n\n"
        "![Example](figure.svg)\n\n```sh\n<not-markup>\n```\n"
    )
    (root / "README.md").write_text(
        "# Repository\n\n## Setup\n\n[![build](https://example.invalid/badge)](https://example.invalid/)\n"
    )
    (root / "docs/figure.svg").write_text("<svg/>")
    monkeypatch.setattr(builder, "ROOT", root)
    monkeypatch.setattr(builder, "OUTPUT", output)
    monkeypatch.setattr(builder, "WHEELS", wheels)
    builder._site({"version": "0.5.0", "wheels": []})
    assert 'href="docs/"' in (root / "site/index.html").read_text()
    assert 'href="docs/accessibility/"' in (root / "site/index.html").read_text()
    landing = (root / "site/docs/index.html").read_text()
    guide = (root / "site/docs/guide/index.html").read_text()
    assert 'href="guide/#same-heading"' in landing
    assert 'id="same-heading"' in guide
    assert 'id="same-heading-1"' in guide
    assert 'id="same-heading-1-1"' in guide
    assert 'href="../repository/#setup"' in guide
    assert guide.count('href="../repository/#setup"') == 2
    assert (root / "site/docs/repository/index.html").is_file()
    assert "example.invalid" not in (root / "site/docs/repository/index.html").read_text()
    assert (root / "site/docs/files/docs/figure.svg").read_text() == "<svg/>"
    index = json.loads((root / "site/docs/search-index.json").read_text())
    assert any(item["url"] == "repository/#setup" for item in index)
    assert 'id="docs-search"' in guide
    assert "&lt;not-markup&gt;" in guide
    assert "<not-markup>" not in guide
    assert 'href="../../"' in guide
    assert "https://simonvanlierde.com/citesync/og.png?v=" in guide


def test_all_documentation_links_and_anchors_resolve(tmp_path: Path):
    (tmp_path / "index.html").write_text((ROOT / "playground/index.html").read_text())
    builder._docs(tmp_path, "assets/test")
    assert (tmp_path / "docs/decisions/index.html").is_file()
    assert not (tmp_path / "docs/decisions/0000-template/index.html").exists()
    pages = {path: Links(path.read_text()) for path in (tmp_path / "docs").rglob("*.html")}
    expected = {path.relative_to(ROOT / "docs") for path in (ROOT / "docs").rglob("*.md")}
    assert len(pages) > len(expected)
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


def test_documentation_titles_and_anchors_preserve_inline_commands(tmp_path: Path):
    builder._docs(tmp_path, "assets/test")
    menu = (tmp_path / "docs/index.html").read_text()
    for command in ("check", "init", "write"):
        title = f"How citesync {command} works"
        guide = (tmp_path / f"docs/{command}/index.html").read_text()
        assert f">{title}</a>" in menu
        assert f"<title>{title} — citesync documentation</title>" in guide
        assert f'id="how-citesync-{command}-works"' in guide
        assert f"<code>citesync {command}</code>" in guide


def test_every_documentation_page_has_its_own_share_metadata(tmp_path: Path):
    builder._docs(tmp_path, "assets/test")
    for path in (tmp_path / "docs").rglob("*.html"):
        parsed = Links(path.read_text())
        canonical = "https://simonvanlierde.com/citesync/" + path.parent.relative_to(tmp_path).as_posix() + "/"
        assert parsed.canonical == canonical
        assert parsed.meta.get("og:url") == canonical, path
        assert parsed.meta.get("og:type") == "website", path
        assert parsed.meta.get("og:title"), path
        assert parsed.meta.get("og:description") == parsed.description, path
        image = urlsplit(parsed.meta.get("og:image") or "")
        assert image.scheme == "https", path
        assert image.netloc == "simonvanlierde.com", path
        assert image.path == "/citesync/og.png", path
        assert parsed.meta.get("og:image:alt"), path
        assert parsed.meta.get("twitter:card") == "summary_large_image", path


def test_missing_documentation_link_stops_the_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs/README.md").write_text("# Documentation\n\n[Missing guide](missing.md)\n")
    monkeypatch.setattr(builder, "ROOT", tmp_path)
    with pytest.raises(ValueError, match=r"linked file does not exist: missing\.md"):
        builder._docs(tmp_path / "site", "assets/test")


def test_search_index_targets_published_sections_and_includes_full_text(tmp_path: Path):
    builder._docs(tmp_path, "assets/test")
    index = json.loads((tmp_path / "docs/search-index.json").read_text())
    assert any("uv tool install citesync" in section["text"] for section in index)
    assert any(section["url"].startswith("changelog/#") for section in index)
    for section in index:
        url = urlsplit(section["url"])
        assert not url.scheme
        assert not url.netloc
        assert not url.path.startswith("/")
        target = (tmp_path / "docs" / unquote(url.path) / "index.html").resolve()
        assert target.is_file(), section
        assert unquote(url.fragment) in Links(target.read_text()).ids, section
    for page in (tmp_path / "docs").rglob("*.html"):
        for link in Links(page.read_text()).links:
            assert not (
                link.startswith("https://github.com/simonvanlierde/citesync/blob/main/")
                and ".md" in urlsplit(link).path
            ), (page, link)


def test_getting_started_is_a_task_guide_and_repository_badges_stay_off_site(tmp_path: Path):
    builder._docs(tmp_path, "assets/test")
    guide = (tmp_path / "docs/getting-started/index.html").read_text()
    assert '<h1 id="getting-started">Getting started</h1>' in guide
    assert "uv tool install citesync" in guide
    repository = (tmp_path / "docs/repository/index.html").read_text()
    assert "<img" not in repository
    assert 'href="https://pypi.org/project/citesync/"' not in repository


def test_documentation_descriptions_follow_the_page_and_escape_markup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    builder._docs(tmp_path, "assets/test")
    config = Links((tmp_path / "docs/config/index.html").read_text()).description
    dataset = Links((tmp_path / "docs/datasets/index.html").read_text()).description
    assert config
    assert config.startswith("Configuration. citesync reads")
    assert dataset
    assert "dataset" in dataset
    assert config != dataset
    assert len(config) <= 160
    assert len(dataset) <= 160
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    (root / "docs/README.md").write_text('# Alpha & "Beta"\n\nUse <literal> & "quoted" values.\n')
    monkeypatch.setattr(builder, "ROOT", root)
    builder._docs(root / "site", "assets/test")
    html = (root / "site/docs/index.html").read_text()
    assert 'content="Alpha &amp; &quot;Beta&quot;. Use &lt;literal&gt; &amp; &quot;quoted&quot; values."' in html

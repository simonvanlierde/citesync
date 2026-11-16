"""Build the current wheel and bundle its locked pure-Python dependencies for the browser."""

# ruff: noqa: INP001

import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from html import escape
from html.parser import HTMLParser
from os.path import relpath
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import urlopen

from markdown_it import MarkdownIt
from markdown_it.token import Token
from packaging.markers import Marker, default_environment
from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "playground"
WHEELS = OUTPUT / "wheels"


def main() -> None:
    """Produce a same-origin wheel bundle and runtime manifest from uv.lock."""
    WHEELS.mkdir(exist_ok=True)
    for old in WHEELS.glob("*.whl"):
        old.unlink()
    subprocess.run(["uv", "build", "--wheel", "--out-dir", str(WHEELS)], cwd=ROOT, check=True)  # noqa: S603, S607
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    locked = {p["name"]: p for p in tomllib.loads((ROOT / "uv.lock").read_text())["package"]}
    environment: dict[str, str] = {key: str(value) for key, value in default_environment().items()} | {
        "python_version": "3.14",
        "python_full_version": "3.14.0",
        "sys_platform": "emscripten",
        "platform_machine": "wasm32",
    }
    queue = [Requirement(r).name for r in project["dependencies"]]
    seen = set()
    while queue:
        name = queue.pop()
        if name in seen:
            continue
        seen.add(name)
        package = locked[name]
        wheel = next(w for w in package["wheels"] if w["url"].endswith("-none-any.whl"))
        url = wheel["url"]
        if not url.startswith("https://files.pythonhosted.org/"):
            msg = "Browser wheels must come from the locked PyPI artifacts."
            raise ValueError(msg)
        with urlopen(url, timeout=60) as response:  # noqa: S310
            content = response.read()
        if hashlib.sha256(content).hexdigest() != wheel["hash"].removeprefix("sha256:"):
            msg = f"Hash mismatch for {name}"
            raise ValueError(msg)
        (WHEELS / url.rsplit("/", 1)[1]).write_bytes(content)
        for dependency in package.get("dependencies", []):
            marker = dependency.get("marker")
            if not marker or Marker(marker).evaluate(environment):
                queue.append(dependency["name"])
    manifest = {
        "version": project["version"],
        "wheels": [
            {"name": p.name, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()} for p in sorted(WHEELS.glob("*.whl"))
        ],
    }
    (OUTPUT / "runtime.json").write_text(json.dumps(manifest) + "\n")
    package = ROOT / "src" / "citesync"
    pin = dict(
        line.split(maxsplit=1)
        for line in (package / "MAPPING_SOURCE").read_text().splitlines()
        if line.startswith(("tag ", "commit "))
    )
    mapping = json.loads((package / "mapping-local.json").read_text())
    (OUTPUT / "lookup.json").write_text(json.dumps({"rows": mapping["rows"], **pin}) + "\n")
    _site(manifest)


def _site(manifest: dict[str, object]) -> None:
    assets = (
        "style.css",
        "fonts/plex-sans-latin.woff2",
        "fonts/plex-sans-latin-ext.woff2",
        "fonts/plex-sans-vietnamese.woff2",
        "fonts/plex-sans-greek.woff2",
        "fonts/plex-sans-cyrillic.woff2",
        "fonts/plex-sans-cyrillic-ext.woff2",
        "docs-search.mjs",
        "theme.mjs",
        "main.mjs",
        "detect.mjs",
        "picker.mjs",
        "lookup.mjs",
        "lookup.json",
        "worker.mjs",
        "runtime.json",
    )
    digest = hashlib.sha256(json.dumps(manifest).encode())
    for name in assets:
        digest.update((OUTPUT / name).read_bytes())
    folder = "assets/" + digest.hexdigest()[:16]
    site = ROOT / "site"
    if site.exists():
        shutil.rmtree(site)
    target = site / folder
    target.mkdir(parents=True)
    for name in assets:
        (target / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OUTPUT / name, target / name)
    shutil.copytree(WHEELS, target / "wheels")
    html = (OUTPUT / "index.html").read_text().replace("<!-- footer -->", _footer("./", str(manifest["version"])))
    html = html.replace('"main.mjs"', f'"{folder}/main.mjs"').replace('"style.css"', f'"{folder}/style.css"')
    html = html.replace('"theme.mjs"', f'"{folder}/theme.mjs"')
    html = html.replace('href="https://simonvanlierde.com/citesync/docs/', 'href="docs/')
    # Platforms cache a link preview by image URL, so the card URL carries the PNG's hash.
    card = hashlib.sha256((OUTPUT / "og.png").read_bytes()).hexdigest()[:8]
    html = html.replace('/og.png"', f'/og.png?v={card}"')
    (site / "index.html").write_text(html)
    for name in ("favicon.svg", "og.png"):
        shutil.copyfile(OUTPUT / name, site / name)
    _docs(site, folder, card, str(manifest["version"]))


def _footer(prefix: str, version: str) -> str:
    return (
        (OUTPUT / "footer.html")
        .read_text()
        .replace("https://simonvanlierde.com/citesync/", prefix)
        .replace("{version}", escape(version))
    )


def _doc_target(source: Path, link: str) -> Path | None:
    """Resolve repository links, including absolute links copied from GitHub."""
    url = urlsplit(link)
    prefix = "https://github.com/simonvanlierde/citesync/blob/main/"
    if link.startswith(prefix):
        return (ROOT / unquote(url.path.removeprefix("/simonvanlierde/citesync/blob/main/"))).resolve()
    if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
        return None
    return (source.parent / unquote(url.path)).resolve()


def _doc_link(source: Path, link: str, pages: dict[Path, Path], *, image: bool = False) -> str:
    """Keep guides and local assets on the website; source-code links stay external."""
    url = urlsplit(link)
    target = _doc_target(source, link)
    if target is None:
        return link
    if not target.is_relative_to(ROOT) or not target.is_file():
        msg = f"{source.relative_to(ROOT)}: linked file does not exist: {link}"
        raise ValueError(msg)
    if target in pages and not image:
        path = Path(relpath(pages[target].parent, pages[source].parent)).as_posix() + "/"
    elif image or target.suffix.lower() in {".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif"}:
        path = Path(relpath(Path("docs/files") / target.relative_to(ROOT), pages[source].parent)).as_posix()
    else:
        path = "https://github.com/simonvanlierde/citesync/blob/main/" + target.relative_to(ROOT).as_posix()
    return urlunsplit(("", "", path, url.query, url.fragment))


def _without_badges(tokens: list[Token]) -> list[Token]:
    """Omit badge-only paragraphs that would contact third-party hosts."""
    for index in range(len(tokens) - 3, -1, -1):
        if tokens[index].type != "paragraph_open":
            continue
        children = tokens[index + 1].children or []
        if any(child.type == "image" for child in children):
            badge = all(
                child.type in {"link_open", "link_close", "image", "softbreak"}
                or (child.type == "text" and not child.content.strip())
                for child in children
            )
            if badge:
                del tokens[index : index + 3]

    return tokens


def _doc_html(_renderer: object, tokens: list[Token], index: int, *_args: object) -> str:
    """Hide author comments; render all other raw HTML as literal text."""
    content = tokens[index].content
    if content.lstrip().startswith("<!--"):
        content = re.sub(r"<!--.*?(?:-->|$)", "", content, flags=re.DOTALL)
    return escape(content)


def _doc_body(source: Path, pages: dict[Path, Path]) -> tuple[str, str]:
    """Render Markdown tokens with stable heading anchors and site-relative links."""
    markdown = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])
    markdown.add_render_rule(
        "table_open",
        lambda *_: '<div class="table-scroll" role="region" aria-label="Scrollable table" tabindex="0"><table>\n',
    )
    markdown.add_render_rule("table_close", lambda *_: "</table></div>\n")
    markdown.add_render_rule("html_block", _doc_html)
    markdown.add_render_rule("html_inline", _doc_html)
    tokens = markdown.parse(source.read_text())
    if not any(token.type == "heading_open" and token.tag == "h1" for token in tokens):
        heading = source.stem.replace("_", " ").replace("-", " ")
        tokens = markdown.parse(f"# {heading[:1].upper() + heading[1:]}\n\n") + tokens
    if source == ROOT / "README.md":
        tokens = _without_badges(tokens)
    title = source.stem
    headings: set[str] = set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            text = "".join(
                child.content
                if child.type in {"text", "code_inline", "image"}
                else " "
                if child.type in {"softbreak", "hardbreak"}
                else ""
                for child in tokens[index + 1].children or []
            )
            base = re.sub(r"[^\w -]", "", text.lower()).replace(" ", "-")
            anchor = base
            count = 0
            while anchor in headings:
                count += 1
                anchor = f"{base}-{count}"
            headings.add(anchor)
            token.attrSet("id", anchor)
            if token.tag == "h1":
                title = text
        for child in token.children or []:
            if child.type == "link_open" and (href := child.attrGet("href")):
                child.attrSet("href", _doc_link(source, str(href), pages))
            elif child.type == "image" and (href := child.attrGet("src")):
                child.attrSet("src", _doc_link(source, str(href), pages, image=True))
    return markdown.renderer.render(tokens, markdown.options, {}), title


class _Sections(HTMLParser):
    """Read rendered text so search and section links share the published anchors."""

    def __init__(self, body: str):
        super().__init__()
        self.sections: list[dict[str, str]] = []
        self.heading = False
        self.feed(body)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.sections.append({"anchor": dict(attrs).get("id") or "", "heading": "", "text": ""})
            self.heading = True
        elif self.sections and tag in {"p", "li", "pre", "tr", "td", "th", "br"}:
            self.sections[-1]["text"] += " "

    def handle_endtag(self, tag: str) -> None:
        if tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.heading = False

    def handle_data(self, data: str) -> None:
        if self.sections:
            self.sections[-1]["heading" if self.heading else "text"] += data


def _doc_pages(site: Path) -> dict[Path, Path]:
    """Collect linked guides and bundle their local images."""
    sources = sorted((ROOT / "docs").rglob("*.md"))
    pages = {
        source: Path("docs")
        / source.relative_to(ROOT / "docs").parent
        / ("" if source.name in {"README.md", "index.md"} else source.stem)
        / "index.html"
        for source in sources
    }
    for source, route in (
        (ROOT / "README.md", "repository"),
        (ROOT / "playground/README.md", "playground"),
        (ROOT / "CHANGELOG.md", "changelog"),
        (ROOT / ".github/CONTRIBUTING.md", "contributing"),
        (ROOT / ".github/CODE_OF_CONDUCT.md", "code-of-conduct"),
        (ROOT / ".github/SECURITY.md", "security"),
    ):
        if source.is_file():
            pages[source] = Path("docs") / route / "index.html"
    pending = list(pages)
    files: set[Path] = set()
    while pending:
        source = pending.pop()
        for token in MarkdownIt("commonmark").parse(source.read_text()):
            for child in token.children or []:
                link = child.attrGet("href") if child.type == "link_open" else child.attrGet("src")
                target = _doc_target(source, str(link)) if link else None
                if target is None or not target.is_file() or not target.is_relative_to(ROOT):
                    continue
                if target.suffix.lower() == ".md" and target not in pages:
                    pages[target] = Path("docs/reference") / target.relative_to(ROOT).with_suffix("") / "index.html"
                    pending.append(target)
                elif child.type == "image" or target.suffix.lower() in {
                    ".png",
                    ".svg",
                    ".jpg",
                    ".jpeg",
                    ".webp",
                    ".gif",
                }:
                    files.add(target)
    for source in files:
        target = site / "docs/files" / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return pages


def _doc_menu(source: Path, pages: dict[Path, Path], rendered: dict[Path, tuple[str, str]], prefix: str) -> str:
    """Group the primary guides and mark the active page or section."""
    groups = (
        ("Start here", ("README.md", "getting-started.md", "../playground/README.md")),
        ("Use citesync", ("init.md", "check.md", "write.md", "datasets.md", "export.md", "pandoc.md")),
        ("Reference", ("config.md", "formats.md", "rules.md", "output.md", "contributions.md")),
        (
            "Project",
            (
                "tested-repositories.md",
                "decisions/index.md",
                "../.github/CONTRIBUTING.md",
                "../CHANGELOG.md",
                "roadmap.md",
                "accessibility.md",
            ),
        ),
    )
    links = ""
    for label, names in groups:
        entries = ""
        for name in names:
            item = (ROOT / "docs" / name).resolve()
            if item not in pages:
                continue
            current = (
                ' aria-current="page"'
                if item == source
                else ' aria-current="location"'
                if item.parent.is_relative_to(ROOT / "docs")
                and item.parent != ROOT / "docs"
                and source.is_relative_to(item.parent)
                else ""
            )
            display_title = (
                "Repository guide"
                if item == ROOT / "README.md"
                else "Browser playground"
                if item == ROOT / "playground/README.md"
                else rendered[item][1]
            )
            href = escape(prefix + pages[item].parent.as_posix()) + "/"
            entries += f'<li><a href="{href}"{current}>{escape(display_title)}</a></li>'
        links += f'<div class="docs-nav-group"><p>{label}</p><ul class="docs-menu">{entries}</ul></div>'
    return links


def _docs(site: Path, assets: str, card: str = "", version: str = "") -> None:
    """Publish and index the Markdown guides beside the playground."""
    pages = _doc_pages(site)
    rendered = {source: _doc_body(source, pages) for source in pages}
    index: list[dict[str, str]] = []
    for source, destination in pages.items():
        body, title = rendered[source]
        sections = _Sections(body).sections
        route = destination.parent.relative_to("docs").as_posix()
        index.extend(
            {
                "title": title,
                "heading": section["heading"],
                "text": " ".join(section["text"].split()),
                "url": (route + "/" if route != "." else "") + "#" + section["anchor"],
            }
            for section in sections
        )
        prefix = Path(relpath(".", destination.parent)).as_posix() + "/"
        links = _doc_menu(source, pages, rendered, prefix)
        outline = "".join(
            f'<li><a href="#{escape(section["anchor"])}">{escape(section["heading"])}</a></li>'
            for section in sections[1:]
        )
        contents = (
            f'<details class="docs-outline"><summary>On this page</summary><ul>{outline}</ul></details>'
            if outline
            else ""
        )
        introduction = " ".join(sections[0]["text"].split()) if sections else ""
        description = f"{title}. {introduction}".strip()
        if len(description) > 160:
            description = description[:157].rsplit(" ", 1)[0] + "…"
        canonical = "https://simonvanlierde.com/citesync/" + destination.parent.as_posix() + "/"
        image = "https://simonvanlierde.com/citesync/og.png" + (f"?v={card}" if card else "")
        html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; script-src 'self'; connect-src 'self'; style-src 'self';
img-src 'self'; font-src 'self'; base-uri 'none'; form-action 'none'">
<title>{escape(title)} — citesync documentation</title>
<meta name="description"
content="{escape(description)}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="citesync">
<meta property="og:title" content="{escape(title)} — citesync documentation">
<meta property="og:description" content="{escape(description)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt"
content="citesync converts package metadata into a CITATION.cff. simonvanlierde.com/citesync">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<script src="{prefix}{assets}/theme.mjs"></script>
<link rel="stylesheet" href="{prefix}{assets}/style.css">
<script type="module" src="{prefix}{assets}/docs-search.mjs"></script>
</head>
<body class="docs-page">
<a class="skip" href="#doc-content">Skip to documentation</a>
<div class="wrap">
<header><a class="brand" href="{prefix}">citesync</a><p>Software citation metadata.</p>
<nav class="site-nav" aria-label="Site"><a href="{prefix}">Playground</a>
<a href="{prefix}docs/" aria-current="page">Documentation</a></nav></header>
<div class="docs-layout">
<aside class="docs-sidebar" aria-label="Documentation tools">
<section class="docs-search" aria-label="Search documentation" data-root="{prefix}docs/" data-state="loading" hidden>
<label for="docs-search">Search documentation</label>
<input id="docs-search" type="search" placeholder="Search guides, commands and fields"
autocomplete="off" aria-describedby="docs-search-status">
<p id="docs-search-status" role="status">Loading search…</p>
<button id="docs-search-retry" type="button" hidden>Retry search</button>
<ol id="docs-search-results" aria-label="Search results" aria-describedby="docs-search-more" hidden></ol>
<p id="docs-search-more" hidden></p>
</section>
<nav aria-label="Documentation pages"><div class="docs-nav-desktop">{links}</div>
<details class="docs-guides"><summary>Browse documentation</summary>
{links}</details></nav>
</aside>
<main id="doc-content" class="doc-content" tabindex="-1">
{contents}<article>{body}</article>
</main>
</div>
<footer aria-label="About citesync">{_footer(prefix, version)}</footer>
</div>
</body>
</html>
"""
        target = site / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)
    (site / "docs/search-index.json").write_text(json.dumps(index, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()

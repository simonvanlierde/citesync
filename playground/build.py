"""Build the current wheel and bundle its locked pure-Python dependencies for the browser."""

# ruff: noqa: INP001

import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from html import escape
from os.path import relpath
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit
from urllib.request import urlopen

from markdown_it import MarkdownIt
from markdown_it.renderer import RendererHTML
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
        shutil.copyfile(OUTPUT / name, target / name)
    shutil.copytree(WHEELS, target / "wheels")
    html = (OUTPUT / "index.html").read_text()
    html = html.replace('"main.mjs"', f'"{folder}/main.mjs"').replace('"style.css"', f'"{folder}/style.css"')
    html = html.replace('href="https://simonvanlierde.com/citesync/docs/"', 'href="docs/"')
    # Platforms cache a link preview by image URL, so the card URL carries the PNG's hash.
    card = hashlib.sha256((OUTPUT / "og.png").read_bytes()).hexdigest()[:8]
    html = html.replace('/og.png"', f'/og.png?v={card}"')
    (site / "index.html").write_text(html)
    for name in ("favicon.svg", "og.png"):
        shutil.copyfile(OUTPUT / name, site / name)
    _docs(site, folder)


def _doc_link(source: Path, link: str, pages: dict[Path, Path], *, image: bool = False) -> str:
    """Keep published guides local and link repository files to their source."""
    url = urlsplit(link)
    if url.scheme or url.netloc or not url.path or url.path.startswith("/"):
        return link
    target = (source.parent / unquote(url.path)).resolve()
    if not target.is_file():
        msg = f"{source.relative_to(ROOT)}: linked file does not exist: {link}"
        raise ValueError(msg)
    if target in pages and not image:
        directory = Path(relpath(pages[target].parent, pages[source].parent)).as_posix()
        path = directory + "/"
    else:
        repository = (
            "https://raw.githubusercontent.com/simonvanlierde/citesync/main/"
            if image
            else "https://github.com/simonvanlierde/citesync/blob/main/"
        )
        path = repository + target.relative_to(ROOT).as_posix()
    return urlunsplit(("", "", path, url.query, url.fragment))


def _doc_body(source: Path, pages: dict[Path, Path]) -> tuple[str, str]:
    """Render Markdown tokens with stable heading anchors and site-relative links."""
    markdown = MarkdownIt("commonmark", {"html": False}).enable(["table", "strikethrough"])
    tokens = markdown.parse(source.read_text())
    title = source.stem
    headings: set[str] = set()
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            text = RendererHTML().renderInlineAsText(tokens[index + 1].children, markdown.options, {})
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


def _docs(site: Path, assets: str) -> None:
    """Publish the existing Markdown guides beside the playground."""
    sources = sorted((ROOT / "docs").rglob("*.md"))
    pages = {
        source: Path("docs")
        / source.relative_to(ROOT / "docs").parent
        / ("" if source.name in {"README.md", "index.md"} else source.stem)
        / "index.html"
        for source in sources
    }
    rendered = {source: _doc_body(source, pages) for source in sources}
    menu = [
        source for source in sources if source.parent == ROOT / "docs" or source == ROOT / "docs/decisions/index.md"
    ]
    for source, destination in pages.items():
        body, title = rendered[source]
        prefix = Path(relpath(".", destination.parent)).as_posix() + "/"
        links = "".join(
            f'<li><a href="{escape(prefix + pages[item].parent.as_posix())}/"'
            + (' aria-current="page"' if item == source else "")
            + f">{escape(rendered[item][1])}</a></li>"
            for item in menu
        )
        canonical = "https://simonvanlierde.com/citesync/" + destination.parent.as_posix() + "/"
        html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy"
content="default-src 'none'; style-src 'self'; img-src 'self' https:; base-uri 'none'; form-action 'none'">
<title>{escape(title)} — citesync documentation</title>
<meta name="description"
content="Guides and reference for generating and checking software citation metadata with citesync.">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{prefix}favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="{prefix}{assets}/style.css">
</head>
<body class="docs-page">
<a class="skip" href="#doc-content">Skip to documentation</a>
<div class="wrap">
<header><a class="brand" href="{prefix}">citesync</a><p>Software citation metadata.</p>
<nav class="site-nav" aria-label="Site"><a href="{prefix}">Playground</a>
<a href="{prefix}docs/" aria-current="page">Documentation</a></nav></header>
<main id="doc-content" class="doc-content" tabindex="-1">
<nav aria-label="Documentation pages"><details><summary>Browse documentation</summary>
<ul class="docs-menu">{links}</ul></details></nav>
<article>{body}</article>
</main>
<footer><nav aria-label="Project links">
<a href="https://github.com/simonvanlierde/citesync/blob/main/{source.relative_to(ROOT).as_posix()}">
View this page on GitHub</a> · <a href="https://github.com/simonvanlierde/citesync/issues">Report an issue</a>
</nav></footer>
</div>
</body>
</html>
"""
        target = site / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html)


if __name__ == "__main__":
    main()

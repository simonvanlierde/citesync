"""Stage repository guides for Zensical and publish them beside the playground."""

# ruff: noqa: INP001

import json
import re
import shutil
import subprocess
from os.path import relpath
from pathlib import Path
from urllib.parse import unquote, urlsplit, urlunsplit

from docs_policy import secure_docs
from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "_docs-source"
GITHUB = "https://github.com/simonvanlierde/citesync/blob/main/"
PLAYGROUND = "https://simonvanlierde.com/citesync/"
GUIDES = {
    "README.md": "repository.md",
    "playground/README.md": "playground.md",
    "CHANGELOG.md": "changelog.md",
    ".github/CONTRIBUTING.md": "contributing.md",
    ".github/CODE_OF_CONDUCT.md": "code-of-conduct.md",
    ".github/SECURITY.md": "security.md",
    # Keep reference pages the old renderer linked. Pages omits dot-prefixed directories.
    ".github/pull_request_template.md": "reference/github/pull_request_template.md",
    "tests/contracts/contributions/README.md": "reference/tests/contracts/contributions/README/index.md",
    "tests/fixtures/README.md": "reference/tests/fixtures/README/index.md",
}
IMAGES = {".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif"}
LINK = re.compile(r"(?P<opening>\]\(<?)(?P<target>[^\s)<>]+)(?P<closing>>?(?:\s+[\"'][^\n]*?[\"'])?\))")


def _rewrite_link(match: re.Match[str], source: Path, destination: Path) -> str:
    link = match["target"]
    url = urlsplit(link)
    if link.startswith(GITHUB):
        target = ROOT / unquote(url.path.removeprefix("/simonvanlierde/citesync/blob/main/"))
    elif link.startswith(PLAYGROUND + "docs/"):
        route = url.path.removeprefix("/citesync/docs/").rstrip("/")
        target = ROOT / "docs" / (route + ".md") if route else ROOT / "docs/README.md"
    elif url.scheme or url.netloc or not url.path or url.path.startswith("/"):
        return match[0]
    else:
        target = (source.parent / unquote(url.path)).resolve()

    if not target.is_relative_to(ROOT) or not target.is_file():
        msg = f"{source.relative_to(ROOT)} links to missing file {link}"
        raise ValueError(msg)
    if item := GUIDES.get(target.relative_to(ROOT).as_posix()):
        path = Path(item)
    elif target.is_relative_to(ROOT / "docs") and target.name != "og-card.html":
        path = target.relative_to(ROOT / "docs")
    elif target.suffix.lower() in IMAGES:
        path = Path("files") / target.relative_to(ROOT)
        published = SOURCE / path
        published.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, published)
    else:
        return (
            match["opening"]
            + GITHUB
            + target.relative_to(ROOT).as_posix()
            + (f"#{url.fragment}" if url.fragment else "")
            + match["closing"]
        )

    site_link = urlunsplit(("", "", Path(relpath(path, destination.parent)).as_posix(), url.query, url.fragment))
    return match["opening"] + site_link + match["closing"]


def _changelog_anchor(text: str, headings: set[str]) -> str:
    """Retain the prior version and duplicate-section slugs."""
    base = re.sub(r"[^\w -]", "", text.lower()).replace(" ", "-")
    anchor = base
    suffix = 1
    while anchor in headings:
        anchor = f"{base}-{suffix}"
        suffix += 1
    headings.add(anchor)
    return anchor


def _strip_comment(source: Path, html: str) -> None:
    if not re.fullmatch(r"(?:\s*<!--.*?-->\s*)+", html, re.DOTALL):
        msg = f"{source.relative_to(ROOT)} contains raw HTML"
        raise ValueError(msg)


def _stage_guide(source: Path, destination: Path) -> None:
    """Keep prose in its original file and resolve its links from the published route."""
    lines = source.read_text().splitlines(keepends=True)
    protected = set()
    headings: set[str] = set()
    description = ""
    tokens = MarkdownIt("commonmark", {"html": True}).parse("".join(lines))
    for index, token in enumerate(tokens):
        if token.map is None:
            continue
        start, stop = token.map
        if token.type in {"fence", "code_block"}:
            protected.update(range(start, stop))
        elif token.type == "html_block":
            _strip_comment(source, token.content)
            lines[start:stop] = [""] * (stop - start)
        elif any(child.type == "html_inline" for child in token.children or []):
            msg = f"{source.relative_to(ROOT)} contains raw inline HTML"
            raise ValueError(msg)
        elif token.type == "inline" and token.children:
            kinds = {child.type for child in token.children if child.type != "text" or child.content.strip()}
            if (
                source == ROOT / "README.md"
                and "image" in kinds
                and kinds <= {"link_open", "link_close", "image", "softbreak"}
            ):
                lines[start:stop] = [""] * (stop - start)
            elif not description and index and tokens[index - 1].type == "paragraph_open":
                text = "".join(child.content if child.type != "softbreak" else " " for child in token.children)
                description = text if len(text) <= 160 else text[:157].rsplit(" ", 1)[0] + "…"
        elif source == ROOT / "CHANGELOG.md" and token.type == "heading_open":
            text = "".join(
                child.content
                for child in tokens[index + 1].children or []
                if child.type in {"text", "code_inline", "image"}
            )
            anchor = _changelog_anchor(text, headings)
            lines[start] = lines[start].rstrip("\n") + f" {{#{anchor}}}\n"
    rewritten = [
        line if index in protected else LINK.sub(lambda match: _rewrite_link(match, source, destination), line)
        for index, line in enumerate(lines)
    ]
    output = SOURCE / destination
    output.parent.mkdir(parents=True, exist_ok=True)
    frontmatter = f"---\ndescription: {json.dumps(description, ensure_ascii=False)}\n---\n\n" if description else ""
    output.write_text(frontmatter + "".join(rewritten))


def prepare() -> None:
    """Give Zensical the guides, aliases and local assets in one clean source tree."""
    if SOURCE.exists():
        shutil.rmtree(SOURCE)
    shutil.copytree(ROOT / "docs", SOURCE, ignore=shutil.ignore_patterns("*.md", "og-card.html"))
    for name in ("og.png", "favicon.svg"):
        shutil.copyfile(ROOT / "playground" / name, SOURCE / "assets" / name)
    shutil.copytree(ROOT / "playground/fonts", SOURCE / "assets/fonts")
    for source in (ROOT / "docs").rglob("*.md"):
        _stage_guide(source, source.relative_to(ROOT / "docs"))
    for source, destination in GUIDES.items():
        _stage_guide(ROOT / source, Path(destination))


def build() -> None:
    """Build the pinned shared docs theme into the combined Pages artifact."""
    prepare()
    command = ["uvx", "--exclude-newer", "1 week", "--with", "zensical-ui==0.0.41", "zensical@0.0.74"]
    subprocess.run([*command, "build", "--strict"], cwd=ROOT, check=True)  # noqa: S603
    secure_docs(ROOT / "site/docs", ROOT)


if __name__ == "__main__":
    build()

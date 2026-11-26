"""Apply the site policy to Zensical pages and reject unexpected inline scripts."""

# ruff: noqa: INP001

import base64
import hashlib
import re
import tomllib
from html.parser import HTMLParser
from os.path import relpath
from pathlib import Path

LINK = re.compile(r'(<a\b[^>]*\shref=")https://simonvanlierde\.com/citesync/')
# Zensical's pinned search interface inserts this stylesheet at runtime.
SEARCH_STYLE = "sha256-NwSx/R2V/U4jnW0Tq5pQ53Y/rzPVJ4dqE7D6UTA/J1k="
CHARSET = '<meta charset="utf-8">'


class _InlineScripts(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.digests: set[str] = set()
        self.content: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "script":
            attributes = dict(attrs)
            media_type = (attributes.get("type") or "").strip().lower()
            if "src" not in attributes and media_type not in {"application/json", "application/ld+json"}:
                self.content = []

    def handle_data(self, data: str) -> None:
        if self.content is not None:
            self.content.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.content is not None:
            digest = hashlib.sha256("".join(self.content).encode()).digest()
            self.digests.add("sha256-" + base64.b64encode(digest).decode())
            self.content = None


def script_hashes(html: str) -> set[str]:
    """Hash the exact script text as it appears in the final page."""
    parser = _InlineScripts()
    parser.feed(html)
    parser.close()
    return parser.digests


def secure_docs(site: Path, root: Path) -> None:
    """Put the CSP before executable resources and keep playground links site-relative."""
    metadata = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    footer = (root / "playground/footer.html").read_text().replace("{version}", metadata["version"])
    pinned = set((root / "playground/docs-script-hashes.txt").read_text().splitlines())
    observed: set[str] = set()
    for page in site.rglob("*.html"):
        prefix = Path(relpath(site.parent, page.parent)).as_posix() + "/"
        html = page.read_text().replace("CITESYNC_COLOPHON", footer)
        html = LINK.sub(r"\g<1>" + prefix, html)
        html = html.replace(' style="text-align: right;"', ' class="align-right"')
        if page.relative_to(site).as_posix() == "roadmap/index.html":
            # The previous public roadmap called this section "Before 0.6".
            html = html.replace('<h2 id="current-release">', '<span id="before-06"></span><h2 id="current-release">')
        hashes = script_hashes(html)
        observed.update(hashes)
        policy = "; ".join(
            (
                "default-src 'none'",
                "script-src 'self' 'wasm-unsafe-eval' " + " ".join(f"'{digest}'" for digest in sorted(hashes)),
                f"style-src 'self' '{SEARCH_STYLE}'",
                "img-src 'self' data:",
                "font-src 'self'",
                "connect-src 'self'",
                "worker-src 'self'",
                "base-uri 'none'",
                "form-action 'none'",
            )
        )
        if CHARSET not in html:
            msg = f"{page.relative_to(site)} has no UTF-8 charset declaration"
            raise ValueError(msg)
        tag = f'<meta http-equiv="Content-Security-Policy" content="{policy}">'
        html = html.replace(CHARSET, f"{CHARSET}\n      {tag}", 1)
        page.write_text(html)
    if pinned != observed:
        msg = (
            f"Review changes to docs scripts. New hashes: {sorted(observed - pinned)}. "
            f"Removed: {sorted(pinned - observed)}"
        )
        raise ValueError(msg)

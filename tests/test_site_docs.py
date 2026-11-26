"""The shared template keeps the repository's guide sources and Pages policy."""

import importlib
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def docs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.syspath_prepend(str(ROOT / "playground"))
    builder = importlib.import_module("build_docs")
    monkeypatch.setattr(builder, "SOURCE", tmp_path / "docs")
    return builder


def test_staged_guides_preserve_repository_links_and_legacy_anchors(docs: ModuleType, tmp_path: Path):
    docs.prepare()
    root = tmp_path / "docs"
    home = (root / "README.md").read_text()
    assert "[Use the playground](playground.md)" in home
    assert "(repository.md#pre-commit-hook)" in home
    assert (root / "reference/tests/fixtures/README/index.md").exists()
    assert (root / "files/playground/og.png").is_file()
    assert "img.shields.io" not in (root / "repository.md").read_text()
    changelog = (root / "changelog.md").read_text()
    assert "{#070---2026-11-20}" in changelog
    assert "{#added-1}" in changelog
    assert "Edit that file, not this one" not in (root / "rules.md").read_text()
    assert "blob/main/docs/og-card.html" in (root / "repository.md").read_text()


def test_staging_rejects_missing_links_and_raw_html(docs: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setattr(docs, "ROOT", tmp_path)
    guide = tmp_path / "guide.md"
    guide.write_text("# Guide\n\n[Missing](missing.md)\n")
    with pytest.raises(ValueError, match=r"missing file missing\.md"):
        docs._stage_guide(guide, Path("guide.md"))  # noqa: SLF001
    guide.write_text("# Guide\n\n<script>blocked()</script>\n")
    with pytest.raises(ValueError, match="raw HTML"):
        docs._stage_guide(guide, Path("guide.md"))  # noqa: SLF001


def test_policy_pins_inline_scripts_and_preserves_canonical_links(docs: ModuleType, tmp_path: Path):
    site = tmp_path / "site/docs/config"
    site.mkdir(parents=True)
    (tmp_path / "playground").mkdir()
    (tmp_path / "playground/footer.html").write_text("citesync {version}")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.7.0"\n')
    html = (
        '<meta charset="utf-8">'
        '<link rel="canonical" href="https://simonvanlierde.com/citesync/docs/config/">'
        '<a href="https://simonvanlierde.com/citesync/">Playground</a>'
        '<script>first()</script><script type="application/json">{}</script>'
    )
    page = site / "index.html"
    page.write_text(html)
    policy = importlib.import_module("docs_policy")
    pinned = tmp_path / "playground/docs-script-hashes.txt"
    pinned.write_text("")
    with pytest.raises(ValueError, match="Review changes to docs scripts"):
        docs.secure_docs(site.parent, tmp_path)
    page.write_text(html)
    (digest,) = policy.script_hashes(html)
    pinned.write_text(digest + "\n")
    docs.secure_docs(site.parent, tmp_path)
    output = page.read_text()
    assert f"'{digest}'" in output
    assert output.index("Content-Security-Policy") < output.index("<script>")
    assert 'href="https://simonvanlierde.com/citesync/docs/config/"' in output
    assert '<a href="../../">Playground</a>' in output
    assert "unsafe-inline" not in output

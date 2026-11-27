"""The release notes gate keeps pending changes out of a tagged distribution."""

import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / ".github" / "scripts" / "release-notes.sh"


@pytest.mark.parametrize("pending", ["", "### Added\n\n- Import Maven metadata.\n"])
def test_release_notes_refuse_pending_changes(tmp_path: Path, pending: str) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is needed for the release script")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(
        f"# Changelog\n\n## [Unreleased]\n\n{pending}\n"
        "## [0.7.0] - 2026-11-26\n\n### Added\n\n- Import Composer metadata.\n",
        encoding="utf-8",
    )
    result = subprocess.run([bash, str(SCRIPT), "v0.7.0", str(changelog)], capture_output=True, text=True, check=False)  # noqa: S603
    if pending:
        assert result.returncode == 1
        assert "Unreleased" in result.stderr
        assert not result.stdout
    else:
        assert result.returncode == 0, result.stderr
        assert "Import Composer" in result.stdout


def test_release_notes_require_a_dated_release_heading(tmp_path: Path) -> None:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash is needed for the release script")
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## [Unreleased]\n\n## [0.7.0]\n\n- Import Maven metadata.\n", encoding="utf-8")
    result = subprocess.run([bash, str(SCRIPT), "v0.7.0", str(changelog)], capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 1
    assert "dated" in result.stderr
    assert not result.stdout

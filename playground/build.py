"""Build the current wheel and bundle its locked pure-Python dependencies for the browser."""

# ruff: noqa: INP001

import hashlib
import json
import shutil
import subprocess
import tomllib
from pathlib import Path
from urllib.request import urlopen

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
    _site(manifest)


def _site(manifest: dict[str, object]) -> None:
    assets = ("style.css", "main.mjs", "detect.mjs", "picker.mjs", "worker.mjs", "runtime.json")
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
    (site / "index.html").write_text(html)
    shutil.copyfile(OUTPUT / "favicon.svg", site / "favicon.svg")


if __name__ == "__main__":
    main()

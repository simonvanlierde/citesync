import json
import tomllib

from hypothesis import example, given
from hypothesis import strategies as st

from citesync.playground_exports import package_templates


def test_templates_omit_unusable_names_and_versions_without_inventing_replacements():
    templates, notes = package_templates({"name": "Lens Grind", "version": "nightly"})
    for data in (
        tomllib.loads(templates["pyproject.toml"])["project"],
        tomllib.loads(templates["Cargo.toml"])["package"],
        json.loads(templates["package.json"]),
    ):
        assert "name" not in data
        assert "version" not in data
        assert "dependencies" not in data
    assert not {"name", "version"} & tomllib.loads(templates["Project.toml"]).keys()
    assert not any(line.startswith(("Package:", "Version:")) for line in templates["DESCRIPTION"].splitlines())
    assert len(notes) == 19
    for note in (
        "DESCRIPTION: Package omitted; use letters, numbers and dots, starting with a letter.",
        "DESCRIPTION: Version omitted; R needs two or more numbers, such as 1.4.0.",
        "Project.toml: name omitted; a Julia package name is an identifier, such as Lensgrind.",
        "Project.toml: version omitted: semver has no spelling for nightly",
        "typst.toml: name omitted; use lower-case letters, numbers and hyphens, such as lensgrind.",
        "typst.toml: version omitted: semver has no spelling for nightly",
        "_extension.yml: version omitted: semver has no spelling for nightly",
    ):
        assert note in notes
    assert "version" not in templates["_extension.yml"]
    assert "authors" not in tomllib.loads(templates["typst.toml"]).get("package", {})
    assert "typst.toml: add authors, license, description; typst/packages requires them." in notes
    assert "typst.toml: add a handle or email to each author." not in notes
    assert json.loads(templates["package.json"])["private"] is True
    assert "build-system" not in tomllib.loads(templates["pyproject.toml"])


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=80))
@example("Quotes \" and ' and \\paths\nnew line\r\t")
def test_package_serializers_round_trip_description(text: str):
    templates, _ = package_templates({"name": "lensgrind", "description": text})
    assert tomllib.loads(templates["pyproject.toml"])["project"]["description"] == text
    assert tomllib.loads(templates["Cargo.toml"])["package"]["description"] == text
    assert json.loads(templates["package.json"])["description"] == text

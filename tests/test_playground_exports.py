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
    assert len(notes) == 13
    assert json.loads(templates["package.json"])["private"] is True
    assert "build-system" not in tomllib.loads(templates["pyproject.toml"])


@given(st.text(alphabet=st.characters(blacklist_categories=("Cs",)), min_size=1, max_size=80))
@example("Quotes \" and ' and \\paths\nnew line\r\t")
def test_package_serializers_round_trip_description(text: str):
    templates, _ = package_templates({"name": "lensgrind", "description": text})
    assert tomllib.loads(templates["pyproject.toml"])["project"]["description"] == text
    assert tomllib.loads(templates["Cargo.toml"])["package"]["description"] == text
    assert json.loads(templates["package.json"])["description"] == text

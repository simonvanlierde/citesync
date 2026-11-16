"""Dataset CodeMeta keeps its resource type when created and rewritten."""

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import given
from hypothesis import strategies as st

from citesync.formats import codemeta_is_dataset

if TYPE_CHECKING:
    from tests.conftest import Run


@pytest.fixture
def dataset(tmp_path: Path, run: "Run") -> Path:
    (tmp_path / "CITATION.cff").write_text(
        "cff-version: 1.2.0\nmessage: Cite this software.\ntitle: Tidepool\nauthors:\n  - family-names: Curie\n",
        encoding="utf-8",
    )
    (tmp_path / "citesync.toml").write_text('dataset-license = "CC0-1.0"\n', encoding="utf-8")
    assert run("write", "--root", str(tmp_path), "-q")[0] == 0
    return tmp_path / "dataset.codemeta.json"


@pytest.mark.parametrize("key", ["@type", "type"])
@pytest.mark.parametrize("kind", [None, "SoftwareSourceCode", ["CreativeWork", "SoftwareSourceCode"]])
def test_write_repairs_existing_dataset_type(dataset: Path, run: "Run", key: str, kind: object) -> None:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    del data["@type"]
    if kind is not None:
        data[key] = kind
    dataset.write_text(json.dumps(data), encoding="utf-8")
    code, out, _ = run("check", "--root", str(dataset.parent))
    assert code == 1
    assert "dataset-type-mismatch" in out
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    fixed = json.loads(dataset.read_text(encoding="utf-8"))
    assert fixed[key if kind is not None else "@type"] == (
        [*kind, "https://schema.org/Dataset"] if isinstance(kind, list) else "https://schema.org/Dataset"
    )
    assert run("check", "--root", str(dataset.parent), "-q")[0] == 0


@pytest.mark.parametrize("key", ["@type", "type"])
@pytest.mark.parametrize(
    "kind",
    [
        "schema:Dataset",
        "http://schema.org/Dataset",
        "https://schema.org/Dataset",
        ["CreativeWork", "schema:Dataset"],
    ],
)
def test_write_preserves_valid_dataset_type(dataset: Path, run: "Run", key: str, kind: object) -> None:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    del data["@type"]
    data[key] = kind
    dataset.write_text(json.dumps(data), encoding="utf-8")
    before = dataset.read_bytes()
    assert run("check", "--root", str(dataset.parent), "-q")[0] == 0
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    assert dataset.read_bytes() == before


def test_repair_preserves_other_dataset_types(dataset: Path, run: "Run") -> None:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    data["@type"] = ["https://example.org/Archive", "SoftwareSourceCode"]
    dataset.write_text(json.dumps(data), encoding="utf-8")
    assert run("check", "--root", str(dataset.parent), "-q")[0] == 1
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    assert json.loads(dataset.read_text(encoding="utf-8"))["@type"] == [*data["@type"], "https://schema.org/Dataset"]


@pytest.mark.parametrize("override", [{"type": "https://example.org/type"}, None])
def test_an_inline_context_can_remap_the_type_alias(dataset: Path, run: "Run", override: object) -> None:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    data["@context"] = [data["@context"], override]
    del data["@type"]
    data["type"] = "Dataset"
    dataset.write_text(json.dumps(data), encoding="utf-8")
    code, out, _ = run("check", "--root", str(dataset.parent))
    assert code == 1
    assert "dataset-type-mismatch" in out
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    fixed = json.loads(dataset.read_text(encoding="utf-8"))
    assert fixed["@type"] == "https://schema.org/Dataset"
    assert fixed["type"] == "Dataset"


def test_a_later_codemeta_context_restores_the_type_alias(dataset: Path, run: "Run") -> None:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    data["@context"] = [{"type": "https://example.org/type"}, data["@context"]]
    del data["@type"]
    data["type"] = "schema:Dataset"
    dataset.write_text(json.dumps(data), encoding="utf-8")
    before = dataset.read_bytes()
    assert run("check", "--root", str(dataset.parent), "-q")[0] == 0
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    assert dataset.read_bytes() == before


@pytest.mark.parametrize(
    ("kind", "override"),
    [
        ("Dataset", {}),
        ("schema:Dataset", {"schema": "https://example.org/"}),
        ("schema:Dataset", {"schema": {"@id": "https://example.org/", "@prefix": True}}),
        ("Dataset", {"Dataset": "https://example.org/Dataset"}),
        ("Dataset", {"Dataset": None}),
        ("Dataset", {"@vocab": "https://example.org/"}),
    ],
)
def test_inline_context_cannot_disguise_a_dataset_type(
    dataset: Path, run: "Run", kind: str, override: dict[str, object]
) -> None:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    data["@context"] = [data["@context"], override]
    data["@type"] = kind
    dataset.write_text(json.dumps(data), encoding="utf-8")
    code, out, _ = run("check", "--root", str(dataset.parent))
    assert code == 1
    assert "dataset-type-mismatch" in out
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    fixed = json.loads(dataset.read_text(encoding="utf-8"))
    assert fixed["@type"] == "https://schema.org/Dataset"
    assert run("check", "--root", str(dataset.parent), "-q")[0] == 0
    before = dataset.read_bytes()
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    assert dataset.read_bytes() == before


@pytest.mark.parametrize(
    "override",
    [
        {"@vocab": "https://schema.org/"},
        {"Dataset": "http://schema.org/Dataset"},
        {"Dataset": {"@id": "schema:Dataset"}},
    ],
)
def test_bare_dataset_requires_an_explicit_schema_definition(
    dataset: Path, run: "Run", override: dict[str, object]
) -> None:
    data = json.loads(dataset.read_text(encoding="utf-8"))
    data["@context"] = [data["@context"], override]
    data["@type"] = "Dataset"
    dataset.write_text(json.dumps(data), encoding="utf-8")
    before = dataset.read_bytes()
    assert run("check", "--root", str(dataset.parent), "-q")[0] == 0
    assert run("write", "--root", str(dataset.parent), "-q")[0] == 0
    assert dataset.read_bytes() == before


@pytest.mark.parametrize(
    ("contexts", "kind", "expected"),
    [
        (["https://w3id.org/codemeta/3.0", None], "schema:Dataset", False),
        ([None, "https://w3id.org/codemeta/3.0"], "schema:Dataset", True),
        ([{"schema": "https://example.org/"}, "https://w3id.org/codemeta/3.0"], "schema:Dataset", True),
        (["https://w3id.org/codemeta/3.0", {"Dataset": None, "@vocab": "https://schema.org/"}], "Dataset", False),
        (
            ["https://w3id.org/codemeta/3.0", {"schema": {"@id": "https://schema.org/", "@prefix": False}}],
            "schema:Dataset",
            False,
        ),
        (
            ["https://w3id.org/codemeta/3.0", {"schema": {"@id": "https://schema.org/", "@prefix": True}}],
            "schema:Dataset",
            True,
        ),
        (
            ["https://w3id.org/codemeta/3.0", {"Dataset": "schema:Dataset"}, {"schema": "https://example.org/"}],
            "Dataset",
            True,
        ),
        ([{"Dataset": "https://example.org/Dataset"}, "https://w3id.org/codemeta/3.0"], "Dataset", False),
    ],
)
def test_dataset_type_context_order(contexts: list[object], kind: str, *, expected: bool) -> None:
    assert codemeta_is_dataset({"@context": contexts, "@type": kind}) is expected


@given(st.lists(st.one_of(st.none(), st.text(), st.dictionaries(st.text(), st.text()))))
def test_explicit_dataset_iris_do_not_depend_on_context(contexts: list[object]) -> None:
    for kind in ("http://schema.org/Dataset", "https://schema.org/Dataset"):
        assert codemeta_is_dataset({"@context": contexts, "@type": kind})

import json
from pathlib import Path
from typing import NoReturn
from urllib.parse import quote

import pytest
from hypothesis import given
from hypothesis import strategies as st

from citesync.cite_sources import doi
from citesync.cli import main
from citesync.codecs import doi_decode
from citesync.errors import CheckError
from citesync.formats import codemeta_is_dataset


def test_cite_crossref_cli(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    url = "https://api.crossref.org/works/10.12345%2FExample"

    def fetch(request_url: str) -> tuple[int, bytes]:
        assert request_url == url
        return 200, json.dumps(
            {
                "message": {
                    "DOI": "10.12345/Example",
                    "title": ["Paper about lens calibration"],
                    "type": "journal-article",
                    "author": [{"given": "Ada", "family": "Valence", "ORCID": "https://orcid.org/0000-0002-1825-0097"}],
                    "published": {"date-parts": [[2025, 4]]},
                }
            }
        ).encode()

    monkeypatch.setattr("citesync.cite_http.fetch", fetch)
    assert main(["cite", "https://doi.org/10.12345%2FExample", "--format", "csl-json"]) == 0
    output = json.loads(capsys.readouterr().out)[0]
    assert output["type"] == "article-journal"
    assert output["DOI"] == "10.12345/Example"
    assert output["issued"] == {"date-parts": [[2025, 4]]}


@pytest.fixture
def responses() -> dict[str, tuple[int, bytes]]:
    crossref = "https://api.crossref.org/works/"
    datacite = "https://api.datacite.org/dois/"
    work = "https://api.openalex.org/works/W1234"
    revision = "d" * 40
    payloads = {
        crossref + "10.12345%2FPaper": {
            "message": {
                "DOI": "10.12345/Paper",
                "title": ["Lens calibration with open instruments"],
                "type": "journal-article",
                "author": [
                    {
                        "given": "Ada",
                        "family": "Valence",
                        "ORCID": "https://orcid.org/0000-0002-1825-0097",
                        "role": [{"vocabulary": "credit", "role": "software"}],
                    },
                    {"name": "Lens Methods Group"},
                ],
                "container-title": ["Journal of Lens Methods"],
                "published": {"date-parts": [[2025, 4, 9]]},
            }
        },
        work: {
            "id": "https://openalex.org/W1234",
            "doi": "https://doi.org/10.12345/Paper",
            "authorships": [
                {
                    "author": {"id": "https://openalex.org/A1234", "orcid": "https://orcid.org/0000-0002-1825-0097"},
                    "contributor_roles": [
                        {"id": "https://openalex.org/contributor-roles/software", "display_name": "Software"}
                    ],
                },
                {"author": None, "raw_author_name": "A. Valence", "contributor_roles": []},
            ],
        },
        work + "/references": {
            "references": [
                {"raw_reference_string": "Lens calibration data", "raw_doi": "10.12345/Data", "work_id": None},
                {
                    "raw_reference_string": "Lens software release",
                    "raw_doi": "10.12345/Software",
                    "work_id": "https://openalex.org/W4567",
                },
                {"raw_reference_string": "Laboratory notebook with no identifier", "raw_doi": None, "work_id": None},
            ]
        },
        "https://api.github.com/repos/lens-methods/lens-calibration/commits?per_page=1": [{"sha": revision}],
    }
    for suffix, kind, title in [
        ("Software", "Software", "Lens calibration software"),
        ("Data", "Dataset", "Lens calibration data"),
    ]:
        payloads[datacite + "10.12345%2F" + suffix] = {
            "data": {
                "attributes": {
                    "doi": "10.12345/" + suffix,
                    "types": {"resourceTypeGeneral": kind},
                    "titles": [{"title": title}],
                    "publicationYear": 2025,
                    "version": "1.2.0",
                    "url": "https://example.org/releases/" + suffix,
                    "creators": [{"name": "Lens Methods Group", "nameType": "Organizational"}],
                    "relatedIdentifiers": [
                        {
                            "relatedIdentifier": "10.12345/Concept",
                            "relatedIdentifierType": "DOI",
                            "relationType": "IsVersionOf",
                        }
                    ],
                }
            }
        }

    result = {url: (200, json.dumps(data).encode()) for url, data in payloads.items()}
    result[crossref + "10.12345%2FSoftware"] = (404, b"")
    result[crossref + "10.12345%2FData"] = (404, b"")
    result[f"https://raw.githubusercontent.com/lens-methods/lens-calibration/{revision}/CITATION.cff"] = (
        200,
        b"""cff-version: 1.2.0
message: Please cite this software.
type: software
title: Lens calibration software
doi: 10.12345/Software
authors:
  - name: Lens Methods Group
preferred-citation:
  type: article
  title: Lens calibration with open instruments
  doi: 10.12345/Paper
  journal: Journal of Lens Methods
  start: 3
  end: 9
  year: 2025
  authors:
    - given-names: Ada
      family-names: Valence
      orcid: https://orcid.org/0000-0002-1825-0097
""",
    )
    result["https://export.arxiv.org/api/query?id_list=2510.01234v2"] = (
        200,
        b"""<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
<entry><id>http://arxiv.org/abs/2510.01234</id><title>Lens calibration with open instruments</title>
<published>2025-10-09T00:00:00Z</published><author><name>Ada Valence</name></author>
<arxiv:doi>10.12345/Paper</arxiv:doi><arxiv:primary_category term="physics.ins-det"/>
<link rel="alternate" href="https://arxiv.org/abs/2510.01234v2"/></entry></feed>""",
    )
    return result


def test_shared_citation_example(
    responses: dict[str, tuple[int, bytes]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
):
    monkeypatch.setattr("citesync.cite_http.fetch", responses.__getitem__)
    library = tmp_path / "capture"
    args = ["cite", "10.12345/Paper", "--json", "--openalex", "W1234"]
    assert main([*args, "--save-responses", str(library)]) == 0
    paper = json.loads(capsys.readouterr().out)
    assert [author["name"] for author in paper["work"]["record"]["author"]] == ["Ada Valence", "Lens Methods Group"]
    author = paper["work"]["record"]["author"][0]
    assert author["orcid"] == "0000-0002-1825-0097"
    assert paper["work"]["attribution"][0]["roles"] == [{"vocabulary": "credit", "role": "software"}]
    observed = paper["openalex"]["authorships"][0]
    assert observed["orcid"].endswith(author["orcid"])
    assert observed["contributor_roles"][0]["display_name"] == "Software"
    matrix_path = Path(__file__).parent / "contracts/contributions/matrix-attribution.json"
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    matrix_claim = next(item for item in matrix["author"] if item.get("schema:author") == observed["orcid"])
    assert matrix_claim["roleName"].rstrip("/").rsplit("/", 1)[-1] == "software"
    assert paper["openalex"]["references"][-1]["work_id"] is None

    for release_doi, kind in [("10.12345/Software", "software"), ("10.12345/Data", "dataset")]:
        assert main(["cite", release_doi, "--json", "--format", "ris"]) == 0
        release = json.loads(capsys.readouterr().out)
        assert release["work"]["kind"] == kind
        assert release["work"]["record"]["version"] == "1.2.0"
        assert release["work"]["record"]["author"][0]["organization"]
        assert release["work"]["related"]["isVersionOf"] == ["10.12345/Concept"]
        assert "openalex" not in release

    repo = "https://github.com/lens-methods/lens-calibration"
    assert main(["cite", repo, "--preferred", "--json"]) == 0
    github = json.loads(capsys.readouterr().out)
    assert github["selected"] == "preferred"
    assert github["work"]["record"]["identifier"] == "10.12345/Software"
    assert github["work"]["preferred"]["record"]["identifier"] == "10.12345/Paper"
    assert github["work"]["preferred"]["record"]["pages"] == "3-9"
    assert github["work"]["revision"] == "d" * 40

    assert main(["cite", "https://arxiv.org/abs/2510.01234v2", "--json"]) == 0
    preprint = json.loads(capsys.readouterr().out)
    assert preprint["work"]["kind"] == "preprint"
    assert preprint["work"]["record"]["arxiv"] == "2510.01234v2"
    assert preprint["work"]["related"]["journalDoi"] == "10.12345/Paper"
    assert "identifier" not in preprint["work"]["record"]
    assert "primaryClass = {physics.ins-det}" in preprint["citation"]["text"]

    def offline(url: str) -> NoReturn:
        pytest.fail(f"offline replay tried to fetch {url}")

    monkeypatch.setattr("citesync.cite_http.fetch", offline)
    assert main([*args, "--replay", str(library)]) == 0
    assert json.loads(capsys.readouterr().out) == paper

    (library / "response-2.bin").write_bytes(b"corrupted")
    assert main([*args, "--replay", str(library)]) == 3
    assert "checksum differs" in json.loads(capsys.readouterr().out)["errors"][0]["message"]


def test_crossref_outage_does_not_fall_back(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    called = []

    def unavailable(url: str) -> NoReturn:
        called.append(url)
        msg = "crossref unavailable (HTTP 503)"
        raise CheckError(msg)

    monkeypatch.setattr("citesync.cite_http.fetch", unavailable)
    assert main(["cite", "doi:10.12345/Paper", "--json"]) == 3
    assert called == ["https://api.crossref.org/works/10.12345%2FPaper"]
    assert "unavailable" in json.loads(capsys.readouterr().out)["errors"][0]["message"]


@pytest.mark.parametrize(
    "value", ["file:///etc/passwd", "https://github.com/a/b/issues", "not-a-doi", "https://example.org/a/b"]
)
def test_unsupported_identifier_is_usage_error(value: str, capsys: pytest.CaptureFixture[str]):
    with pytest.raises(SystemExit, match="2"):
        main(["cite", value, "--json"])
    assert json.loads(capsys.readouterr().out)["errors"]


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789%/", min_size=1, max_size=80))
def test_bare_doi_keeps_literal_percent_and_case(suffix: str):
    bare = "10.12345/" + suffix
    assert doi(bare) == bare
    assert doi("https://doi.org/" + quote(bare, safe="/")) == bare


def test_repository_main_survives_unsupported_preferred(
    responses: dict[str, tuple[int, bytes]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    cff = next(url for url in responses if url.endswith("CITATION.cff"))
    responses[cff] = (200, responses[cff][1].replace(b"type: article", b"type: book"))
    monkeypatch.setattr("citesync.cite_http.fetch", responses.__getitem__)
    args = ["cite", "https://github.com/lens-methods/lens-calibration", "--json"]
    assert main(args) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["work"]["kind"] == "software"
    assert result["work"]["preferred"] is None
    assert result["work"]["preferred_issue"]
    assert main([*args, "--preferred"]) == 3


def test_cite_codemeta_preserves_literal_percent_in_doi(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    raw_doi = "10.12345/a%2Fb"
    url = quote(raw_doi, safe="")
    payload = {"doi": raw_doi, "titles": [{"title": "Lens data"}], "types": {"resourceTypeGeneral": "Dataset"}}
    requests = {
        f"https://api.crossref.org/works/{url}": (404, b""),
        f"https://api.datacite.org/dois/{url}": (200, json.dumps({"data": {"attributes": payload}}).encode()),
    }
    monkeypatch.setattr("citesync.cite_http.fetch", requests.__getitem__)
    assert main(["cite", raw_doi, "--format", "codemeta"]) == 0
    codemeta = json.loads(capsys.readouterr().out)
    assert codemeta["identifier"] == "https://doi.org/10.12345/a%252Fb"
    assert doi(codemeta["identifier"]) == raw_doi
    assert doi_decode(codemeta["identifier"]) == raw_doi
    assert codemeta_is_dataset(codemeta)


def test_cite_repository_reads_codemeta_dataset(
    responses: dict[str, tuple[int, bytes]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    cff = next(url for url in responses if url.endswith("CITATION.cff"))
    codemeta = {"@context": "https://w3id.org/codemeta/3.0", "@type": "schema:Dataset", "name": "Lens data"}
    responses[cff] = (404, b"")
    responses[cff.removesuffix("CITATION.cff") + "codemeta.json"] = (200, json.dumps(codemeta).encode())
    monkeypatch.setattr("citesync.cite_http.fetch", responses.__getitem__)
    assert main(["cite", "https://github.com/lens-methods/lens-calibration", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["work"]["kind"] == "dataset"


def test_capture_refuses_linked_response(
    responses: dict[str, tuple[int, bytes]],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
):
    monkeypatch.setattr("citesync.cite_http.fetch", responses.__getitem__)
    capture = tmp_path / "capture"
    args = ["cite", "10.12345/Paper", "--json"]
    assert main([*args, "--save-responses", str(capture)]) == 0
    capsys.readouterr()
    response = capture / "response-1.bin"
    saved = tmp_path / "body"
    response.rename(saved)
    try:
        response.symlink_to(saved)
    except OSError:
        pytest.skip("symlinks unavailable")
    assert main([*args, "--replay", str(capture)]) == 3
    assert "expected a regular file" in json.loads(capsys.readouterr().out)["errors"][0]["message"]


def test_cite_reviewed_openalex_match(
    responses: dict[str, tuple[int, bytes]], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    monkeypatch.setattr("citesync.cite_http.fetch", responses.__getitem__)
    assert main(["cite", "https://openalex.org/W1234", "--json"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["input"] == {"provider": "openalex", "value": "W1234"}
    assert result["work"]["record"]["identifier"] == "10.12345/Paper"
    assert [row["provider"] for row in result["provenance"]["responses"]] == ["openalex", "crossref"]

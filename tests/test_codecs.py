"""Property tests on every codec: decode(encode(x)) == x for normalised values, and decoding is idempotent."""

from hypothesis import example, given
from hypothesis import strategies as st

from citesync import codecs

SPDX = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,30}", fullmatch=True)
ORCID = st.from_regex(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]", fullmatch=True)
DOI = st.from_regex(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]{1,30}", fullmatch=True)
WORD = st.from_regex(r"[A-Za-zÀ-ÿ'][A-Za-zÀ-ÿ' -]{0,20}[A-Za-zÀ-ÿ']", fullmatch=True).map(lambda s: " ".join(s.split()))
NUMBER = r"(0|[1-9][0-9]{0,2})"
PRE_RELEASE = st.from_regex(rf"{NUMBER}(\.{NUMBER}){{0,3}}(a|b|rc){NUMBER}", fullmatch=True)


@given(SPDX)
def test_license_round_trip(spdx: str) -> None:
    assert codecs.license_decode(codecs.license_encode(spdx, "spdx")) == spdx
    assert codecs.license_decode(codecs.license_encode(spdx, "spdx-url")) == spdx
    # Zenodo's form loses case, so it round-trips up to the comparison key.
    assert codecs.license_key(codecs.license_decode(codecs.license_encode(spdx, "zenodo")) or "") == spdx.casefold()


@given(st.text())
@example("https://spdx.org/licenses/MIT.html")
@example("http://spdx.org/licenses/Apache-2.0/")
@example({"text": "MIT"})
@example({"file": "LICENSE"})
def test_license_decode_idempotent(raw: object) -> None:
    once = codecs.license_decode(raw)
    assert codecs.license_decode(once) == once


@given(ORCID)
def test_orcid_round_trip(orcid: str) -> None:
    assert codecs.orcid_decode(codecs.orcid_encode(orcid, "url")) == orcid
    assert codecs.orcid_decode(codecs.orcid_encode(orcid, "bare")) == orcid


@given(st.text())
@example("https://orcid.org/0000-0002-1825-009x")
@example("http://www.orcid.org/0000-0002-1825-0097/")
@example("/")
@example("https://orcid.org/")
def test_orcid_decode_idempotent(raw: str) -> None:
    once = codecs.orcid_decode(raw)
    assert codecs.orcid_decode(once) == once


@given(DOI)
def test_doi_round_trip(doi: str) -> None:
    assert codecs.doi_decode(codecs.doi_encode(doi, "bare")) == doi
    assert codecs.doi_decode(codecs.doi_encode(doi, "url")) == doi


@given(st.text())
@example("doi:10.5281/zenodo.1")
@example("https://dx.doi.org/10.5281/ZENODO.1")
@example("doi:")
@example("https://doi.org/")
def test_doi_decode_idempotent(raw: str) -> None:
    once = codecs.doi_decode(raw)
    assert codecs.doi_decode(once) == once


@given(st.text())
@example("git+https://github.com/o/r.git/")
@example("https://github.com/o/r.git.git")
@example("/")
def test_repo_decode_idempotent(raw: str) -> None:
    once = codecs.repo_decode(raw)
    assert codecs.repo_decode(once) == once


def test_repo_decode_strips_npm_spelling() -> None:
    assert codecs.repo_decode("git+https://github.com/o/r.git") == "https://github.com/o/r"


def test_repo_decode_expands_npm_shorthands() -> None:
    for raw in ("github:o/r", "git@github.com:o/r.git", "git+ssh://git@github.com/o/r.git"):
        assert codecs.repo_decode(raw) == "https://github.com/o/r", raw
    assert codecs.repo_decode("gitlab:o/r") == "https://gitlab.com/o/r"
    assert codecs.repo_decode("bitbucket:o/r") == "https://bitbucket.org/o/r"


def test_doi_decode_keeps_only_doi_shaped_values() -> None:
    assert codecs.doi_decode("https://github.com/o/r") is None
    assert codecs.doi_decode(["https://github.com/o/r", "https://doi.org/10.1/a", "10.1/b"]) == "10.1/a"


def test_license_decode_list() -> None:
    assert codecs.license_decode(["MIT", "https://spdx.org/licenses/Apache-2.0"]) == "MIT OR Apache-2.0"
    assert codecs.license_decode([]) is None


def test_name_key_nfc() -> None:
    assert codecs.name_key("Jose\u0301") == codecs.name_key("Jos\u00e9")


@given(WORD.filter(lambda s: "," not in s), WORD.filter(lambda s: "," not in s))
def test_zenodo_name_round_trip(given_name: str, family: str) -> None:
    assert codecs.zenodo_name_decode(codecs.zenodo_name_encode(given_name, family)) == (given_name, family)
    assert codecs.zenodo_name_decode(codecs.zenodo_name_encode(None, family)) == (None, family)


@given(st.text())
@example("van Lierde, Simon")
@example("Family , Given  Name")
@example("No Comma")
def test_zenodo_name_decode_idempotent(raw: str) -> None:
    once = codecs.zenodo_name_decode(raw)
    if once is not None and once[0] is not None:
        assert codecs.zenodo_name_decode(codecs.zenodo_name_encode(*once)) == once


@given(WORD)
@example("Ada Lovelace")
def test_contact_name(name: str) -> None:
    assert codecs.contact_name_decode(f"{name} <ada@example.org> (https://example.org)") == name
    assert codecs.contact_name_decode(f"{name} <ada@example.org>") == name
    assert codecs.contact_name_decode(name) == name
    assert codecs.contact_name_decode(codecs.contact_name_decode(name)) == name


@given(PRE_RELEASE)
def test_version_semver_round_trip(version: str) -> None:
    assert codecs.version_key(codecs.version_encode_semver(version)) == version


@given(st.text())
@example("0.3.1-rc.1")
@example("1.0.0-beta")
@example("2.0.0-alpha.3+build.5")
@example("1.0.0.pre1")
@example("0a1\u0660")  # an Arabic-Indic zero is not a version digit
def test_version_key_idempotent(raw: str) -> None:
    once = codecs.version_key(raw)
    assert codecs.version_key(once) == once


def test_version_key_examples() -> None:
    assert codecs.version_key("0.3.1-rc.1") == "0.3.1rc1"
    assert codecs.version_key("1.0.0-beta") == "1.0.0b0"
    assert codecs.version_key("1.2.3") == "1.2.3"

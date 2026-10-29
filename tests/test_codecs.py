"""Property tests on every codec: decode(encode(x)) == x for normalised values, and decoding is idempotent."""

import re
from collections.abc import Callable

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from citesync import codecs
from citesync.errors import CannotWrite

SPDX = st.from_regex(r"[A-Za-z0-9][A-Za-z0-9.+-]{0,30}", fullmatch=True)
ORCID = st.from_regex(r"[0-9]{4}-[0-9]{4}-[0-9]{4}-[0-9]{3}[0-9X]", fullmatch=True)
DOI = st.from_regex(r"10\.[0-9]{4,9}/[A-Za-z0-9._;()/:-]{1,30}", fullmatch=True)
WORD = st.from_regex(r"[A-Za-zÀ-ÿ'][A-Za-zÀ-ÿ' -]{0,20}[A-Za-zÀ-ÿ']", fullmatch=True).map(lambda s: " ".join(s.split()))
NUMBER = r"(0|[1-9][0-9]{0,2})"
PRE_RELEASE = st.from_regex(
    rf"v?{NUMBER}(\.{NUMBER}){{0,2}}((a|b|rc){NUMBER})?(\.dev{NUMBER})?(\+[a-z0-9]{{1,5}})?", fullmatch=True
)


@given(SPDX)
def test_license_round_trip(spdx: str) -> None:
    assert codecs.license_decode(codecs.license_encode(spdx, "spdx")) == spdx
    assert codecs.license_decode(codecs.license_encode(spdx, "spdx-url")) == spdx
    # Zenodo's form loses case, so it round-trips up to the comparison key.
    assert codecs.license_key(codecs.license_decode(codecs.license_encode(spdx, "zenodo")) or "") == spdx.casefold()


def test_license_encode_zenodo_lowercases() -> None:
    assert codecs.license_encode("Apache-2.0", "zenodo") == "apache-2.0"


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
@example("/\r0")
@example("/ /0")
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


SEGMENT = st.from_regex(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,15}", fullmatch=True).filter(
    lambda s: not s.casefold().endswith(".git")
)
REF_TAIL = {
    "github.com": ["/tree/main", "/tree/v1.2.3", "/blob/main/README.md"],
    "gitlab.com": ["/-/tree/main", "/-/blob/v1/src/x.py"],
    "codeberg.org": ["/src/branch/main", "/src/tag/v1.2.3"],
}


@given(st.sampled_from(sorted(REF_TAIL)), SEGMENT, SEGMENT, st.data())
def test_repo_key_spellings_agree(host: str, owner: str, repo: str, data: st.DataObject) -> None:
    """Scheme, host case, www., git+, .git, a trailing slash, a fragment and a ref tail don't change the key."""
    key = codecs.repo_key(f"https://{host}/{owner}/{repo}")
    tail = data.draw(st.sampled_from(["", *REF_TAIL[host]]))
    spelling = data.draw(
        st.sampled_from(
            [
                f"http://www.{host.upper()}/{owner}/{repo}{tail}/",
                f"git+https://{host}/{owner}/{repo}.git",
                f"git://{host}/{owner}/{repo}.git#v1.0",
                f"https://{host}/{owner}/{repo}{tail}?tab=readme",
            ]
        )
    )
    assert codecs.repo_key(spelling) == key
    assert codecs.repo_key(key) == key


@given(st.text())
@example("https://[x/")
@example("https://www.www.github.com/o/r")
@example("https://gitlab.com/x/-.git/-")
@example("https://github.com/o/R.GIT")
def test_repo_key_idempotent(raw: str) -> None:
    once = codecs.repo_key(raw)
    assert codecs.repo_key(once) == once


def test_repo_key_path_case() -> None:
    assert codecs.repo_key("https://github.com/Example/Repo") == "https://github.com/example/repo"
    assert codecs.repo_key("https://gitlab.com/Group/Repo") == "https://gitlab.com/Group/Repo"
    assert codecs.repo_key("https://gitlab.com/g/sub/r/-/tree/main") == "https://gitlab.com/g/sub/r"
    assert codecs.repo_key("https://github.com/tree/r") == "https://github.com/tree/r"  # an owner named tree
    assert codecs.repo_key("https://example.org/o/r/tree/main") == "https://example.org/o/r/tree/main"
    assert codecs.repo_key("https://user@example.org/o/BOX/") == "https://example.org/o/BOX"


@pytest.mark.parametrize(
    ("decode", "raw", "expected"),
    [
        (codecs.orcid_decode, "https://orcid.org/0000-0002-1825-009x/", "0000-0002-1825-009X"),
        (codecs.repo_decode, "https://github.com/o/BOX/", "https://github.com/o/BOX"),
        (codecs.zenodo_name_decode, None, None),
        (codecs.zenodo_name_decode, "  ", None),
        (codecs.contact_name_decode, "Ada <ada", "Ada <ada"),  # no closing >, so the whole string
        (codecs.version_decode, None, None),
        (codecs.version_decode, True, None),
        (codecs.version_decode, {"a": 1}, None),
    ],
)
def test_decode_edge_cases(decode: Callable[[object], object], raw: object, expected: object) -> None:
    assert decode(raw) == expected


def test_doi_decode_keeps_only_doi_shaped_values() -> None:
    assert codecs.doi_decode("https://github.com/o/r") is None
    assert codecs.doi_decode(["https://github.com/o/r", "https://doi.org/10.1/a", "10.1/b"]) == "10.1/a"


def test_doi_decode_reads_property_values() -> None:
    swhid = {"@type": "PropertyValue", "propertyID": "SWHID", "value": "swh:1:dir:" + "0" * 40}
    ror = {"@type": "PropertyValue", "propertyID": "ROR", "url": "https://ror.org/02e2c7k09"}
    assert codecs.doi_decode([swhid, ror]) is None
    assert codecs.doi_decode({"@type": "PropertyValue", "propertyID": "doi", "value": "10.1/a"}) == "10.1/a"
    assert codecs.doi_decode([swhid, {"@type": "PropertyValue", "url": "https://doi.org/10.1/b"}, "10.1/c"]) == "10.1/b"
    assert codecs.doi_decode({"@type": "PropertyValue", "propertyID": "DOI", "value": "doi:10.1/A"}) == "10.1/A"


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


# semver.org's regular expression, without the named groups
SEMVER = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


@given(PRE_RELEASE)
@example("v1.2.3")
@example("1.0")
@example("1.2.3rc1")
@example("1.2.3.dev0")
def test_version_semver_round_trip(version: str) -> None:
    semver = codecs.version_encode_semver(version)
    assert SEMVER.match(semver), semver
    assert codecs.version_key(semver) == codecs.version_key(version)


@pytest.mark.parametrize("version", ["1.2.3.post1", "2!1.0", "1.2.3.4", "unreleased"])
def test_version_semver_cannot_spell(version: str) -> None:
    with pytest.raises(CannotWrite, match=f"semver has no spelling for {re.escape(version)}"):
        codecs.version_encode_semver(version)


@given(st.text())
@example("0.3.1-rc.1")
@example("1.0.0-beta")
@example("2.0.0-alpha.3+build.5")
@example("1.0.0.pre1")
@example("0a1\u0660")  # an Arabic-Indic zero is not a version digit
def test_version_key_idempotent(raw: str) -> None:
    once = codecs.version_key(raw)
    assert codecs.version_key(str(once)) == once


RELEASE = st.from_regex(rf"{NUMBER}(\.{NUMBER}){{0,2}}", fullmatch=True)


@given(RELEASE, st.sampled_from(["a", "b", "rc", "dev"]), st.from_regex(NUMBER, fullmatch=True))
def test_version_key_spellings_agree(release: str, tag: str, n: str) -> None:
    """A leading v, trailing zeros and semver pre-release spelling don't change the key."""
    key = codecs.version_key(f"{release}{tag}{n}" if tag != "dev" else f"{release}.dev{n}")
    semver_tag = {"a": "alpha", "b": "beta"}.get(tag, tag)
    for spelling in (f"v{release}.0-{semver_tag}.{n}", f"{release}-{semver_tag}.{n}"):
        assert codecs.version_key(spelling) == key, spelling


@pytest.mark.parametrize(
    ("a", "b", "equal"),
    [
        ("v1.2.3", "1.2.3", True),
        ("1.0", "1.0.0", True),
        ("1.0.0-dev.1", "1.0.0.dev1", True),
        ("0.3.1-rc.1", "0.3.1rc1", True),
        ("1.0.0-beta", "1.0.0b0", True),
        (" 1.2.3 ", "1.2.3", True),
        ("unreleased", "unreleased", True),
        ("unreleased", "1.0", False),
        ("Unreleased", "unreleased", False),  # not PEP 440, so compared exactly
        ("1.2.3", "1.2.4", False),
    ],
)
def test_version_key_equality(a: str, b: str, *, equal: bool) -> None:
    assert (codecs.version_key(a) == codecs.version_key(b)) is equal


@pytest.mark.parametrize(
    ("a", "b", "equal"),
    [
        ("(MIT OR Apache-2.0)", "mit or apache-2.0", True),
        ("(MIT AND Apache-2.0) OR GPL-3.0", "MIT AND Apache-2.0 OR GPL-3.0", False),
        ("(GPL-2.0 WITH Classpath-exception-2.0) OR MIT", "GPL-2.0 WITH Classpath-exception-2.0 OR MIT", False),
    ],
)
def test_license_key_drops_parentheses_only_around_or(a: str, b: str, *, equal: bool) -> None:
    assert (codecs.license_key(a) == codecs.license_key(b)) is equal


def test_version_encode_semver_spells_a_dev_release() -> None:
    assert codecs.version_encode_semver("1.0.dev3") == "1.0.0-dev.3"


@given(st.lists(st.text("abcXYZ", min_size=1), min_size=1), st.lists(st.sampled_from(["-", "_", " ", "  ", "-_ "])))
def test_spaced_reads_any_separator_run_as_one_space(words: list[str], seps: list[str]) -> None:
    joined = "".join(w + (seps[i % len(seps)] if seps else "-") for i, w in enumerate(words))
    assert codecs.spaced(joined) == " ".join(words)
    assert codecs.spaced(codecs.spaced(joined)) == codecs.spaced(joined)

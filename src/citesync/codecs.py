"""How a value is spelled in each format, as opposed to where it sits (the mapping's job).

Each codec has ``decode``, from what a file holds to the normalised value, and
``encode``, from the normalised value to one of the spellings a format uses.
``key`` gives what two normalised values are compared by.
"""

import re

_SPDX_URL = re.compile(r"^https?://spdx\.org/licenses/(?P<id>[^/]+?)(?:\.html|\.json)?/?$", re.IGNORECASE)
_ORCID_URL = re.compile(r"^https?://(?:www\.)?orcid\.org/", re.IGNORECASE)
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_CONTACT = re.compile(r"^(?P<name>[^<(]*?)\s*(?:<[^>]*>)?\s*(?:\([^)]*\))?$")
_PRE = re.compile(
    r"^(?P<release>\d+(?:\.\d+)*)[-_.]?(?P<tag>alpha|a|beta|b|rc|c|preview|pre)[-_.]?(?P<n>\d*)(?P<local>\+.*)?$",
    re.IGNORECASE | re.ASCII,  # int() would read other scripts' digits too
)
_PEP440_TAG = {"alpha": "a", "a": "a", "beta": "b", "b": "b", "rc": "rc", "c": "rc", "pre": "rc", "preview": "rc"}
_SEMVER_TAG = {"a": "alpha", "b": "beta", "rc": "rc"}


def _clean(text: str) -> str:
    return " ".join(text.split())


# Licence: an SPDX id, an SPDX URL, or Zenodo's lowercase id.


def license_decode(raw: object) -> str | None:
    """The SPDX id in a licence field; PEP 621's legacy ``{text = ...}`` table gives its text."""
    if isinstance(raw, dict):
        raw = raw.get("text")  # a {file = ...} table names a file, not a licence
    if not isinstance(raw, str) or not raw.strip():
        return None
    raw = raw.strip()
    match = _SPDX_URL.match(raw)
    return match["id"] if match else raw


def license_encode(spdx: str, form: str) -> str:
    """``spdx`` as ``"spdx"`` (the id), ``"spdx-url"`` or ``"zenodo"`` (lowercase id: Zenodo's vocabulary)."""
    return {"spdx": spdx, "spdx-url": f"https://spdx.org/licenses/{spdx}", "zenodo": spdx.lower()}[form]


def license_key(spdx: str) -> str:
    """Licences compare case-insensitively, since Zenodo lowercases them."""
    return spdx.casefold()


# ORCID: a URL or a bare iD.


def orcid_decode(raw: object) -> str | None:
    """The bare iD (``0000-0002-1825-0097``), with a final ``x`` upper-cased."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    bare = _ORCID_URL.sub("", raw.strip()).strip("/")
    return bare.upper()


def orcid_encode(orcid: str, form: str) -> str:
    """``orcid`` as ``"url"`` (CFF, codemeta ``@id``) or ``"bare"`` (Zenodo)."""
    return {"url": f"https://orcid.org/{orcid}", "bare": orcid}[form]


# DOI: bare, a doi.org URL or a doi: prefix.


def doi_decode(raw: object) -> str | None:
    """The bare DOI (``10.5281/zenodo.1234567``)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    return _DOI_PREFIX.sub("", raw.strip())


def doi_encode(doi: str, form: str) -> str:
    """``doi`` as ``"bare"`` (CFF, Zenodo) or ``"url"`` (codemeta ``identifier``)."""
    return {"bare": doi, "url": f"https://doi.org/{doi}"}[form]


def doi_key(doi: str) -> str:
    """DOIs are case-insensitive."""
    return doi.casefold()


# Repository URL: strip git+, .git and a trailing slash.


def repo_decode(raw: object) -> str | None:
    """The repository URL without ``git+``, ``.git`` or a trailing slash."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    url = raw.strip().removeprefix("git+")
    while url.endswith(("/", ".git")):
        url = url.rstrip("/").removesuffix(".git")
    return url or None


# Person name: given and family, Zenodo's "Family, Given", or one "Name <email> (url)" string.


def zenodo_name_decode(raw: object) -> tuple[str | None, str] | None:
    """(given, family) from ``"Family, Given"``. Without a comma, the whole string is the family name."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    family, sep, given = raw.partition(",")
    if not sep:
        return None, _clean(family)
    return (_clean(given) or None), _clean(family)


def zenodo_name_encode(given: str | None, family: str) -> str:
    """``"Family, Given"``, or the family name alone."""
    return f"{family}, {given}" if given else family


def contact_name_decode(raw: object) -> str | None:
    """The name in an npm or Cargo person string, ``"Name <email> (url)"``."""
    if not isinstance(raw, str):
        return None
    match = _CONTACT.match(raw.strip())
    name = _clean(match["name"]) if match else _clean(raw)
    return name or None


def display_name(given: str | None, family: str | None) -> str | None:
    """``"Given Family"`` from the parts a format holds."""
    name = _clean(" ".join(part for part in (given, family) if part))
    return name or None


def name_key(name: str) -> str:
    """Names compare case-insensitively, with whitespace collapsed."""
    return _clean(name).casefold()


# Version: semver pre-release tags normalised to PEP 440, so 0.3.1-rc.1 equals 0.3.1rc1.


def version_decode(raw: object) -> str | None:
    """The version as written; YAML may have read ``1.0`` as a number."""
    if raw is None or isinstance(raw, (bool, dict, list)):
        return None
    text = str(raw).strip()
    return text or None


def version_key(version: str) -> str:
    """The PEP 440 spelling of a pre-release: ``0.3.1-rc.1`` is ``0.3.1rc1``, ``1.0.0-beta`` is ``1.0.0b0``."""
    match = _PRE.match(version.strip())
    if not match:
        return version.strip()
    return f"{match['release']}{_PEP440_TAG[match['tag'].lower()]}{int(match['n'] or 0)}{match['local'] or ''}"


def version_encode_semver(version: str) -> str:
    """A PEP 440 pre-release in semver spelling: ``0.3.1rc1`` is ``0.3.1-rc.1``."""
    match = _PRE.match(version)
    if not match:
        return version
    tag = _SEMVER_TAG[_PEP440_TAG[match["tag"].lower()]]
    return f"{match['release']}-{tag}.{int(match['n'] or 0)}{match['local'] or ''}"

"""How a value is spelled in each format, as opposed to where it sits (the mapping's job).

Each codec has ``decode``, from what a file holds to the normalised value, and
``encode``, from the normalised value to one of the spellings a format uses.
``key`` gives what two normalised values are compared by.
"""

import re
import unicodedata
from urllib.parse import urlsplit

from packaging.version import InvalidVersion, Version

from citesync.errors import CannotWrite

_SPDX_URL = re.compile(r"^https?://spdx\.org/licenses/(?P<id>[^/]+?)(?:\.html|\.json)?/?$", re.IGNORECASE)
_ORCID_URL = re.compile(r"^https?://(?:www\.)?orcid\.org/", re.IGNORECASE)
_SLASHES_AND_SPACE = re.compile(r"^[\s/]+|[\s/]+$")  # "/\r0" is "0", as decoding it again gives
_DOI_PREFIX = re.compile(r"^(?:https?://(?:dx\.)?doi\.org/|doi:\s*)", re.IGNORECASE)
_DOI = re.compile(r"^10\.\d+/\S+$")
_NPM_HOSTS = {"github": "github.com", "gitlab": "gitlab.com", "bitbucket": "bitbucket.org"}
_NPM_SHORTHAND = re.compile(r"^(?P<host>github|gitlab|bitbucket):(?P<path>[\w.-]+/[\w.-]+)$")
_SSH = re.compile(r"^(?:ssh://)?git@(?P<host>[^:/]+)[:/](?P<path>.+)$")
# What follows the repository on a forge's web pages: a branch, tag, file or GitLab's /-/ pages.
_OWNER_REPO_TAIL = r"^(/[^/]+/[^/]+)/{}(?:/.*)?$"
_REF_TAIL = {
    "github.com": re.compile(_OWNER_REPO_TAIL.format("(?:tree|blob)")),
    "gitlab.com": re.compile(r"^(/.+?)/-(?:/.*)?$"),  # groups nest, so the repository is everything before /-/
    "codeberg.org": re.compile(_OWNER_REPO_TAIL.format("src")),
    "gitea.com": re.compile(_OWNER_REPO_TAIL.format("src")),
    "bitbucket.org": re.compile(_OWNER_REPO_TAIL.format("src")),
}
_CONTACT = re.compile(r"^(?P<name>[^<(]*?)\s*(?:<[^>]*>)?\s*(?:\([^)]*\))?$")
_SEMVER_TAG = {"a": "alpha", "b": "beta", "rc": "rc"}


def clean(text: str) -> str:
    """Whitespace collapsed to single spaces, and none at either end."""
    return " ".join(text.split())


# Licence: an SPDX id, an SPDX URL, or Zenodo's lowercase id.


def license_decode(raw: object) -> str | None:
    """The SPDX id in a licence field; PEP 621's legacy ``{text = ...}`` table gives its text.

    A list (CFF, codemeta) reads as the SPDX expression ``A OR B``, in the order given.
    """
    if isinstance(raw, list):
        ids = [i for i in map(license_decode, raw) if i]
        return " OR ".join(ids) or None
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
    bare = _SLASHES_AND_SPACE.sub("", _ORCID_URL.sub("", raw.strip()))
    return bare.upper() or None


def orcid_encode(orcid: str, form: str) -> str:
    """``orcid`` as ``"url"`` (CFF, codemeta ``@id``) or ``"bare"`` (Zenodo)."""
    return {"url": f"https://orcid.org/{orcid}", "bare": orcid}[form]


# DOI: bare, a doi.org URL or a doi: prefix.


def doi_decode(raw: object) -> str | None:
    """The bare DOI (``10.5281/zenodo.1234567``), or None for a value that isn't one.

    codemeta's ``identifier`` may be any URL, a schema.org PropertyValue or a list: the first DOI
    in it counts. A PropertyValue holds a DOI in its ``value`` or ``url`` (``propertyID`` ``DOI``);
    any other, such as a SWHID or ROR id, is ignored.
    """
    if isinstance(raw, dict):
        raw = [raw.get("value"), raw.get("url")]
    if isinstance(raw, list):
        return next(filter(None, map(doi_decode, raw)), None)
    if not isinstance(raw, str):
        return None
    doi = _DOI_PREFIX.sub("", raw.strip())
    return doi if _DOI.match(doi) else None


def doi_encode(doi: str, form: str) -> str:
    """``doi`` as ``"bare"`` (CFF, Zenodo) or ``"url"`` (codemeta ``identifier``)."""
    return {"bare": doi, "url": f"https://doi.org/{doi}"}[form]


def doi_key(doi: str) -> str:
    """DOIs are case-insensitive."""
    return doi.casefold()


# Repository URL: strip git+, .git and a trailing slash.


def repo_decode(raw: object) -> str | None:
    """The repository URL without ``git+``, ``.git`` or a trailing slash.

    npm's shorthands (``github:o/r``) and SSH remotes (``git@github.com:o/r.git``)
    expand to the https URL.
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    url = raw.strip().removeprefix("git+")
    if match := _NPM_SHORTHAND.match(url):
        url = f"https://{_NPM_HOSTS[match['host']]}/{match['path']}"
    elif match := _SSH.match(url):
        url = f"https://{match['host']}/{match['path']}"
    while url.endswith(("/", ".git")):
        url = url.rstrip("/").removesuffix(".git")
    return url or None


def repo_key(url: str) -> str:
    """The repository a URL names, as npm's hosted-git-info reads it: https, the host lowercased without ``www.``.

    No credentials, query, fragment (npm's ``#ref``), ``.git`` or trailing slash. On a known forge, a
    branch, tag or file page names its repository (``/tree/v1.0`` on GitHub, ``/-/...`` on GitLab,
    ``/src/...`` on Codeberg, Gitea and Bitbucket), and on github.com, which ignores case, the path is casefolded.
    """
    try:
        parts = urlsplit(url.strip())
    except ValueError:  # an unbalanced [ in the host
        return url.strip()
    if not parts.netloc:
        return url.strip()
    host = re.sub(r"^(?:www\.)+", "", parts.netloc.rpartition("@")[2].lower())
    path = parts.path.casefold() if host == "github.com" else parts.path
    tail, old = _REF_TAIL.get(host), None
    while path != old:  # until stable: stripping .git can expose a tail, and dropping a tail a .git
        old = path
        path = path.rstrip("/").removesuffix(".git")
        if tail and (match := tail.match(path)):
            path = match[1]
    return f"https://{host}{path}"


# Person name: given and family, Zenodo's "Family, Given", or one "Name <email> (url)" string.


def zenodo_name_decode(raw: object) -> tuple[str | None, str] | None:
    """(given, family) from ``"Family, Given"``. Without a comma, the whole string is the family name."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    family, sep, given = raw.partition(",")
    if not sep:
        return None, clean(family)
    return (clean(given) or None), clean(family)


def zenodo_name_encode(given: str | None, family: str) -> str:
    """``"Family, Given"``, or the family name alone."""
    return f"{family}, {given}" if given else family


def contact_name_decode(raw: object) -> str | None:
    """The name in an npm or Cargo person string, ``"Name <email> (url)"``."""
    if not isinstance(raw, str):
        return None
    match = _CONTACT.match(raw.strip())
    name = clean(match["name"]) if match else clean(raw)
    return name or None


def display_name(given: str | None, family: str | None) -> str | None:
    """``"Given Family"`` from the parts a format holds."""
    name = clean(" ".join(part for part in (given, family) if part))
    return name or None


def name_key(name: str) -> str:
    """Names compare case-insensitively, with whitespace collapsed and Unicode in NFC."""
    return unicodedata.normalize("NFC", clean(name)).casefold()


# Version: equal as PEP 440 versions, so v1.2.3 = 1.2.3, 1.0 = 1.0.0 and 0.3.1-rc.1 = 0.3.1rc1.


def version_decode(raw: object) -> str | None:
    """The version as written; YAML may have read ``1.0`` as a number."""
    if raw is None or isinstance(raw, (bool, dict, list)):
        return None
    text = str(raw).strip()
    return text or None


def version_key(version: str) -> Version | str:
    """The parsed PEP 440 version, or for one that isn't (``unreleased``) the string itself.

    A ``Version`` never equals a ``str``, so a PEP 440 version and anything else differ.
    """
    try:
        return Version(version)
    except InvalidVersion:
        return version.strip()


def version_encode_semver(version: str) -> str:
    """``version`` in semver spelling: ``v1.2rc1`` is ``1.2.0-rc.1``, ``1.0.dev3`` is ``1.0.0-dev.3``.

    Raises:
        CannotWrite: for a version semver has no spelling for: not PEP 440, a post-release,
            an epoch, or more than three release numbers.
    """
    try:
        v = Version(version)
    except InvalidVersion:
        v = None
    if v is None or v.post is not None or v.epoch or len(v.release) > 3:  # semver has major.minor.patch only
        msg = f"semver has no spelling for {version}"
        raise CannotWrite(msg)
    pre = [_SEMVER_TAG[v.pre[0]], v.pre[1]] if v.pre else []
    dev = ["dev", v.dev] if v.dev is not None else []
    suffix = ".".join(map(str, pre + dev))
    release = ".".join(map(str, (*v.release, 0, 0)[:3]))
    return release + (f"-{suffix}" if suffix else "") + (f"+{v.local}" if v.local else "")

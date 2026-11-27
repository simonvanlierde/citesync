"""Fetch citation metadata from known services and replay recorded responses."""

import datetime as dt
import hashlib
import json
import os
import stat
from dataclasses import asdict, dataclass, field
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from citesync.errors import CheckError

_MAX_BYTES = 4_000_000
_MAX_RESPONSES = 10
_HOSTS = {
    "api.crossref.org": "crossref",
    "api.datacite.org": "datacite",
    "export.arxiv.org": "arxiv",
    "api.github.com": "github",
    "raw.githubusercontent.com": "github",
    "api.openalex.org": "openalex",
}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args: object, **_kwargs: object) -> None:
        return None


def fetch(url: str) -> tuple[int, bytes]:
    """Read a bounded response without following redirects or sending credentials."""
    provider = _provider(url)
    request = Request(  # noqa: S310 - _provider checks HTTPS and the full host against the allowlist
        url, headers={"User-Agent": "citesync (https://github.com/simonvanlierde/citesync)"}
    )
    try:
        with build_opener(_NoRedirect()).open(request, timeout=15) as response:
            data = response.read(_MAX_BYTES + 1)
    except HTTPError as err:
        with err:
            if err.code == 404:
                return 404, b""
        msg = f"{provider} unavailable (HTTP {err.code})"
        raise CheckError(msg) from err
    except (URLError, OSError) as err:
        msg = f"{provider} unavailable"
        raise CheckError(msg) from err
    if len(data) > _MAX_BYTES:
        msg = "citation metadata response exceeds 4 MB"
        raise CheckError(msg)
    return 200, data


def _provider(url: str) -> str:
    parsed = urlsplit(url)
    provider = _HOSTS.get(parsed.netloc)
    if provider is None or parsed.scheme != "https" or parsed.fragment:
        msg = "unsupported citation metadata endpoint"
        raise CheckError(msg)
    return provider


@dataclass(frozen=True)
class Response:
    """One response and the evidence needed to verify it."""

    provider: str
    url: str
    status: int
    retrieved_at: str
    sha256: str
    file: str


def _read(path: Path) -> bytes:
    expected = path.lstat()
    msg = f"{path.name}: expected a regular file in the citation capture"
    if not stat.S_ISREG(expected.st_mode):
        raise CheckError(msg)
    # The directory entry can change between inspection and open.
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(expected, opened):
            raise CheckError(msg)
        data = stream.read(_MAX_BYTES + 1)
    if len(data) > _MAX_BYTES:
        msg = f"{path.name}: citation response exceeds 4 MB"
        raise CheckError(msg)
    return data


@dataclass
class Responses:
    """Live metadata response capture, or a replay that never calls the network."""

    mapping: str
    replay: Path | None = None
    _records: dict[str, tuple[Response, bytes]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        if self.replay is None:
            return
        try:
            manifest = json.loads(_read(self.replay / "responses.json"))
            if manifest["schema_version"] != 1 or manifest["mapping_sha256"] != self.mapping:
                msg = "citation capture uses a different schema or mapping"
                raise CheckError(msg)
            rows = manifest["responses"]
            if not isinstance(rows, list) or len(rows) > _MAX_RESPONSES:
                msg = "citation capture has an invalid response list"
                raise CheckError(msg)
            for index, row in enumerate(rows, 1):
                record = Response(**row)
                if not self._valid(record, index):
                    msg = f"citation capture has an invalid response at position {index}"
                    raise CheckError(msg)
                body = _read(self.replay / record.file)
                if hashlib.sha256(body).hexdigest() != record.sha256:
                    msg = f"citation capture checksum differs for {record.file}"
                    raise CheckError(msg)
                self._records[record.url] = record, body
        except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError) as err:
            msg = "cannot read citation capture"
            raise CheckError(msg) from err

    def _valid(self, record: Response, index: int) -> bool:
        url = urlsplit(record.url)
        provider = _HOSTS.get(url.netloc)
        timestamp = dt.datetime.fromisoformat(record.retrieved_at)
        return (
            record.file == f"response-{index}.bin"
            and provider is not None
            and provider == record.provider
            and url.scheme == "https"
            and not url.fragment
            and record.url not in self._records
            and type(record.status) is int
            and record.status in {200, 404}
            and timestamp.utcoffset() == dt.timedelta()
        )

    def get(self, url: str) -> bytes | None:
        """Return response bytes, or None on HTTP 404."""
        provider = _provider(url)
        if url not in self._records:
            if self.replay is not None:
                msg = f"citation capture lacks a response for {provider}"
                raise CheckError(msg)
            status, body = fetch(url)
            record = Response(
                provider,
                url,
                status,
                dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
                hashlib.sha256(body).hexdigest(),
                f"response-{len(self._records) + 1}.bin",
            )
            self._records[url] = record, body
        record, body = self._records[url]
        return body if record.status == 200 else None

    def required(self, url: str) -> bytes:
        """Return response bytes, raising if the provider has no such resource."""
        body = self.get(url)
        if body is None:
            msg = f"no record at {_HOSTS[urlsplit(url).netloc]}"
            raise CheckError(msg)
        return body

    def manifest(self) -> dict[str, object]:
        """Report hashes, URLs and timestamps without embedding provider payloads."""
        return {
            "schema_version": 1,
            "mapping_sha256": self.mapping,
            "responses": [asdict(record) for record, _ in self._records.values()],
        }

    def save(self, destination: Path) -> None:
        """Save raw responses to a new directory and write the manifest last."""
        destination.mkdir()
        for record, body in self._records.values():
            (destination / record.file).write_bytes(body)
        (destination / "responses.json").write_text(json.dumps(self.manifest(), indent=2) + "\n", encoding="utf-8")

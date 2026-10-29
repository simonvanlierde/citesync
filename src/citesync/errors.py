"""The one error citesync raises when it can't check: the CLI turns it into exit 2."""


class CheckError(Exception):
    """A config error, an unreadable file or an unknown format version, with the path named."""

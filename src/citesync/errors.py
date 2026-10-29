"""The errors citesync raises: :class:`CheckError` becomes exit 2, :class:`UnreadableError` a finding.

:class:`CannotWrite` never leaves ``write``: the field is left as it was, and its finding says why.
"""


class CheckError(Exception):
    """A config error, a missing file or a bad mapping, with the path named."""


class UnreadableError(CheckError):
    """A file citesync can't read, parse or use, reported as an ``unreadable`` finding on ``path``.

    ``line`` and ``column`` are 1-based, when the parser gives them.
    """

    def __init__(self, path: str, message: str, line: int | None = None, column: int | None = None) -> None:
        super().__init__(f"{path}{f':{line}:{column}' if line else ''}: {message}")
        self.path, self.message, self.line, self.column = path, message, line, column


class CannotWrite(Exception):  # noqa: N818 - a reason, not a failure: write skips the field
    """A value write can't spell in a file's format without losing something, with the reason."""

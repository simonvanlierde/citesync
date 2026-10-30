"""Edit JSON text by splicing each changed value into it, so everything else keeps its bytes."""

import json
import re
from typing import Any

_DECODER = json.JSONDecoder()


def _skip(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def _node(text: str, i: int) -> tuple[int, int, dict[Any, Any] | None]:
    """The (start, end, children) of the JSON value at ``i``; children by key or index, None for a scalar."""
    i = _skip(text, i)
    opener = text[i]
    if opener not in "[{":
        return i, _DECODER.raw_decode(text, i)[1], None
    kids: dict[Any, Any] = {}
    j = i + 1
    while True:
        j = _skip(text, j)
        if text[j] in "]}":
            return i, j + 1, kids
        if opener == "{":
            key, end = _DECODER.raw_decode(text, j)
            j = _skip(text, end) + 1  # past the colon
        else:
            key = len(kids)
        kids[key] = _node(text, j)
        j = _skip(text, kids[key][1])
        j += text[j] == ","


def splice(text: str, old: Any, new: Any) -> str:  # noqa: ANN401
    """``text``, the JSON of ``old``, with each value that differs in ``new`` replaced in place."""
    indent = re.search(r"\n([ \t]+)\S", text)
    edits: list[tuple[int, int, str]] = []
    _edits(text, _node(text, 0), old, new, edits, indent[1] if indent else "  ")
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def _edits(text: str, node: tuple[int, int, Any], old: Any, new: Any, edits: list, indent: str) -> None:  # noqa: ANN401
    """Collect a replacement for each smallest value that differs between ``old`` and ``new``."""
    start, end, kids = node
    if type(old) is type(new) and old == new:
        return
    if isinstance(old, dict) and isinstance(new, dict) and list(old) == list(new):
        for key in old:
            _edits(text, kids[key], old[key], new[key], edits, indent)
    elif isinstance(old, list) and isinstance(new, list) and len(old) == len(new):
        for i, (a, b) in enumerate(zip(old, new, strict=True)):
            _edits(text, kids[i], a, b, edits, indent)
    elif isinstance(old, list) and isinstance(new, list) and old and new[: len(old)] == old:
        # appended to: add after the last element in its layout, leaving the others' text alone
        last_start, last_end, _ = kids[len(old) - 1]
        line = text[text.rfind("\n", 0, last_start) + 1 :]
        margin = line[: len(line) - len(line.lstrip(" \t"))]
        sep = ",\n" + margin if "\n" in text[start:end] else ", "
        multi = "\n" in text[last_start:last_end]
        dumped = (json.dumps(el, indent=indent if multi else None, ensure_ascii=False) for el in new[len(old) :])
        edits.append((last_end, last_end, "".join(sep + d.replace("\n", "\n" + margin) for d in dumped)))
    elif "\n" in text[start:end]:  # a multi-line value stays multi-line, at the indentation of its line
        line = text[text.rfind("\n", 0, start) + 1 :]
        margin = line[: len(line) - len(line.lstrip(" \t"))]
        edits.append((start, end, json.dumps(new, indent=indent, ensure_ascii=False).replace("\n", "\n" + margin)))
    else:
        edits.append((start, end, json.dumps(new, ensure_ascii=False)))

"""Fuzz the JSON writer's round trip and preservation of untouched text."""

import json
import sys

import atheris  # ty: ignore[import-not-found] - installed by the optional fuzz group

with atheris.instrument_imports(include=["citesync.jsonsplice"]):
    from citesync.jsonsplice import splice


def fuzz_splice(data: bytes) -> None:
    """Generate JSON edits from bounded input and check the result against its intended values."""
    provider = atheris.FuzzedDataProvider(data)
    indent = provider.PickValueInList([None, 2, "\t"])
    append_author = provider.ConsumeBool()
    name = provider.ConsumeUnicodeNoSurrogates(128)
    revised_name = provider.ConsumeUnicodeNoSurrogates(128)
    note = "Unchanged: " + provider.ConsumeUnicodeNoSurrogates(128)
    authors = [{"name": name}]
    old = {"note": note, "title": "Draft: " + name, "author": authors}
    new = {
        **old,
        "title": "Release: " + revised_name,
        "author": (authors if append_author else []) + [{"name": revised_name}],
    }
    note_member = f'"note" : {json.dumps(note)}'
    text = json.dumps(old, indent=indent).replace('"note":', '"note" :', 1)
    result = splice(text, old, new)
    assert json.loads(result) == new
    assert note_member in result
    assert splice(result, new, new) == result


if __name__ == "__main__":
    atheris.Setup(sys.argv, fuzz_splice)
    atheris.Fuzz()

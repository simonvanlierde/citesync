"""The JSON splicer: each changed value replaced in place, everything else byte for byte."""

import copy
import json

import pytest

from citesync.jsonsplice import splice

ADA = "https://orcid.org/0000-0002-1825-0097"

BEFORE = """{
    "author": [
        {
            "@type": "Person",
            "@id": "https://orcid.org/0000-0002-1825-0097",
            "name": "Ada Lovelace"
        }
    ],
    "keywords": ["alpha", "beta"],
    "isAccessibleForFree": 1
}
"""

AFTER = """{
    "author": [
        {
            "@type": "Person",
            "@id": "https://orcid.org/0000-0002-1825-0097",
            "name": "Ada Lovelace"
        },
        {
            "@type": "Person",
            "name": "Marie Curie"
        }
    ],
    "keywords": ["alpha", "beta", "gamma"],
    "isAccessibleForFree": true
}
"""


@pytest.mark.parametrize("indent", ["    ", "\t"])
def test_splice_appends_in_the_files_own_layout(indent: str) -> None:
    """A multi-line list grows by multi-line entries at the file's indent, a one-line list stays on one line."""
    text = BEFORE.replace("    ", indent)
    old = json.loads(text)
    new = copy.deepcopy(old)
    new["author"].append({"@type": "Person", "name": "Marie Curie"})
    new["keywords"].append("gamma")
    new["isAccessibleForFree"] = True  # equal to 1 in Python, but not the same JSON
    assert splice(text, old, new) == AFTER.replace("    ", indent)


def test_splice_rewrites_a_changed_multi_line_value_at_its_margin() -> None:
    text = BEFORE.replace("    ", "\t")
    old = json.loads(text)
    new = copy.deepcopy(old)
    new["author"][0] = {"@type": "Person", "givenName": "Ada", "familyName": "Lovelace"}
    new["keywords"] = ["gamma"]
    expected = (
        '{\n\t"author": [\n\t\t{\n\t\t\t"@type": "Person",\n\t\t\t"givenName": "Ada",\n\t\t\t"familyName": "Lovelace"\n'
        '\t\t}\n\t],\n\t"keywords": ["gamma"],\n\t"isAccessibleForFree": 1\n}\n'
    )
    assert splice(text, old, new) == expected


def test_splice_leaves_equal_values_in_their_own_spelling() -> None:
    """Compact JSON too: no space after a colon, no indented line."""
    text = '{"a":["\\u00e9t\\u00e9","beta"],"b":{"c":1.50},"d":1,"e":["x"]}'
    old = json.loads(text)
    new = {**copy.deepcopy(old), "a": ["été", "Skłodowska"], "d": 2, "e": ["x", "Curie", "Skłodowska"]}
    expected = '{"a":["\\u00e9t\\u00e9","Skłodowska"],"b":{"c":1.50},"d":2,"e":["x", "Curie", "Skłodowska"]}'
    assert splice(text, old, new) == expected


def test_splice_with_no_indented_line_indents_by_two() -> None:
    text = '{"a": [\n1\n]}'
    assert splice(text, {"a": [1]}, {"a": {"b": 1}}) == '{"a": {\n  "b": 1\n}}'


@pytest.mark.parametrize(
    ("text", "new", "expected"),
    [
        ('\n  {"a": {"b":\n  1}}', {"a": {"x": 1}}, '\n  {"a": {\n    "x": 1\n  }}'),
        ('\n  {"c": [{"d":\n  1}]}', {"c": [{"d": 1}, {"e": 2}]}, '\n  {"c": [{"d":\n  1},\n  {\n    "e": 2\n  }]}'),
    ],
    ids=["replaced", "appended"],
)
def test_splice_on_the_line_after_a_blank_first_line(text: str, new: object, expected: str) -> None:
    """The margin is found back to the newline at offset 0."""
    assert splice(text, json.loads(text), new) == expected

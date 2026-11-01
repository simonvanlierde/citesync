# Carry contribution records through citation files

A CodeMeta document can hold people and contribution roles. Citesync compares the
people across files and preserves the roles in CodeMeta. It does not translate a
CRediT role into a Zenodo contributor type.

## The record each tool supplies

| Tool or format | Supplies or preserves | Limit |
| --- | --- | --- |
| CRediT Matrix | Author `Role` objects linked by ORCID, with the CRediT URL in `roleName` | Its current role export supplies no Person records, skips non-authors and authors without ORCIDs, and omits contribution scores |
| CodeMeta | Separate author and contributor people, plus roles | Each role needs its linked Person; keep the original CRediT Matrix project file for scores |
| citesync | Reads people using the pinned codemeta-drift mapping; preserves existing role objects and extra person metadata | It cannot create missing identity information or choose a Zenodo contributor type |
| CITATION.cff | Authors, name parts and available ORCIDs | No general contributor list or CRediT role slot |
| .zenodo.json | Creators, typed contributors and existing affiliations | Its contributor types are a different vocabulary from CRediT |

CodeMeta 3 defines `type` and `id` as aliases of `@type` and `@id`.
Citesync reads either spelling for people. When correcting an existing person's
ORCID, it keeps the existing key spelling. Other person identifiers, such as
profile URLs, fragments and blank-node identifiers, are not ORCIDs. Writes keep
these identifiers and refuse to remove a person if that would discard them.
It preserves unknown role URLs too.

The [CRediT Matrix exporter inspected for this contract](https://github.com/simonvanlierde/credit-matrix/blob/b39d3aa992c6779e701a87946cdbf527279e9a69/src/core/export/codemeta.ts)
returns `type: "Role"`, `schema:author` and `roleName`. Its output belongs beside
linked Person records in CodeMeta, not in another file's author list. Supplying
those Person records remains a separate step; the example below supplies them by hand.

## Run the checked example

From a development checkout, run:

```sh
uv run pytest tests/test_contribution_contract.py
```

The [example files](../tests/contracts/contributions/README.md) contain one author
with an ORCID and a software role, one author without an ORCID, and a non-author
contributor with an existing Zenodo type. Name parts include a particle, a hyphen
and non-ASCII characters.

The tests launch the installed CLI against copies in temporary directories. They
compare the written people with hand-checked expected values and verify that a
second write changes nothing. They also check a CodeMeta target rewritten from
CFF, role preservation, correction of an aliased `id`, and a warning for a role
whose linked Person was removed.

A new Zenodo contributor without a chosen type remains a reported mismatch;
write leaves that contributor list intact. An empty or absent target list is
currently treated as missing information and is not populated. A passing check
therefore does not establish that every contribution has reached every format.

This example checks the citesync boundary using the current pinned mapping. It
does not run CRediT Matrix or prove a complete export-and-deposit workflow.

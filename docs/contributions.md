# Carry contribution records through citation files

A CodeMeta document can hold people and contribution roles. Citesync compares the
people across files and preserves the roles in CodeMeta. It does not translate a
CRediT role into a Zenodo contributor type.

## The record each tool supplies

| Tool or format | Supplies or preserves | Limit |
| --- | --- | --- |
| CRediT Matrix (main) | Linked `Person` and `Role` records for authors and non-author contributors | People without ORCIDs use document-local identifiers; keep native Matrix JSON for contribution scores |
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

The [merged Matrix exporter](https://github.com/simonvanlierde/credit-matrix/pull/185)
returns an attribution fragment with linked people and roles. Merge that fragment
into a software CodeMeta document. Local identifiers link roles within that document;
they do not establish a persistent identity across documents. This producer change
is on Matrix main; use a release that includes it before relying on published packages.

[Matrix's integration test](https://github.com/simonvanlierde/credit-matrix/tree/a8a55c648bbb45862d60fbdbd6d51cd75eea3cc3/integrations/codemeta)
runs its built CLI against citesync revision `2a95043`, which includes the
codemeta-drift 0.4.0 mapping. Citesync 0.2.0 predates the required identity fixes.
The test verifies linked people, role preservation, author/contributor separation,
repeat-write idempotence and explicit gaps for missing Zenodo contributor types.
It does not validate a Zenodo deposit.

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
write leaves that contributor list intact. Set
[`zenodo-contributor-type`](config.md) to supply a default for new contributors.
An existing empty target list opts in; an absent list stays absent. A passing check
does not establish that every contribution has reached every format.

The hand-written fixture checks the citesync boundary without installing Matrix.
The [Matrix consumer CI job](../.github/workflows/matrix-consumer.yml) separately
builds and packs the exact merged producer revision `a8a55c6`, then runs the same
people through both installed CLIs. It uses the native Matrix roster and its
hand-checked attribution expectation, with source hashes recorded in the
[fixture notes](../tests/contracts/contributions/README.md).

To run the producer check locally, unpack a `credit-matrix` package tarball and run:

```sh
CREDIT_MATRIX_CLI=/absolute/path/to/package/dist/cli.js uv run --frozen pytest tests/test_matrix_consumer.py
```

The CLI must include Matrix #185. The published npm v0.9.0 package is too old;
the v0.10.0 release candidate and the CI's pinned source build both pass. The
consumer job uses the merged source pin while v0.10.0 is prepared, so PR checks
do not depend on a future registry upload. After publication, the registry tarball
can be checked with the same command. Tests also verify the existing explicit
`zenodo-contributor-type` opt-in, preserve existing types, and leave an absent
contributor field absent. This checks citation files, not a live Zenodo deposit.

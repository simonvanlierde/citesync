# Decisions

Each file here records one decision that shapes this project: what we chose, why, and what it costs.

## Adding a record

1. Copy `0000-template.md` to the next free number and a short slug, such as `0001-one-parser.md`.
2. Fill in its sections. Set its status to `proposed`, then to `accepted` once agreed.
3. Add it to the index below.

Don't rewrite an accepted record. When a decision changes, write a new record, and set the old one's status to `superseded by 0007`, with the new record's number.

## Index

- [0001. Any supported file can be the source](0001-pluggable-source.md): accepted
- [0002. Field locations come from a vendored mapping, in a separate repo](0002-vendored-mapping.md): accepted
- [0003. `write` changes manifests only for fields you list](0003-manifests-opt-in.md): accepted
- [0004. Python 3.13 and ruamel.yaml](0004-python-and-ruamel.md): accepted
- [0005. citesync keeps contribution roles intact and does not interpret them](0005-vocabulary-blind-roles.md): accepted

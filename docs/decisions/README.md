# Decisions

Each file here records one decision that shapes this project: what we chose, why, and what it costs.

## Adding a record

1. Copy `template.md` to a short slug named after the decision, such as `one-parser.md`. No number: parallel branches can't then take the same one.
2. Fill in its sections. Set its status to `proposed`, then to `accepted` once agreed.
3. Add it to the index below.

Don't rewrite an accepted record. When a decision changes, write a new record, and set the old one's status to `superseded by one-parser.md`, with the new record's file name.

## Index

- [Any supported file can be the source](pluggable-source.md): accepted
- [Field locations come from a vendored mapping, in a separate repo](vendored-mapping.md): accepted
- [`write` changes manifests only for fields you list](manifests-opt-in.md): accepted
- [Python 3.12 and ruamel.yaml](python-and-ruamel.md): accepted
- [citesync keeps contribution roles intact and does not interpret them](vocabulary-blind-roles.md): accepted

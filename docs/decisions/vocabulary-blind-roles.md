# citesync keeps contribution roles intact and does not interpret them

- Status: accepted
- Date: 2026-10-29

## Context

CodeMeta can hold people with contribution roles, and CRediT is a common role vocabulary. Zenodo has its own contributor types, a different list. Any CRediT-to-Zenodo mapping loses meaning.

## Decision

citesync stays blind to role vocabularies. CRediT lives in [credit-matrix](https://github.com/simonvanlierde/credit-matrix), which prints CodeMeta `Role` objects. citesync compares the people, and preserves existing `Role` objects and their `roleName` values (a credit.niso.org URL for CRediT).

There is no CRediT-to-Zenodo mapping. A new Zenodo contributor gets its type from the `zenodo-contributor-type` config key, or stays for a hand edit.

## Consequences

- No role is lost or renamed by `write`.
- Zenodo contributors need one configured type or a manual edit.
- The checked people and role contract is in [Contributions](../contributions.md).

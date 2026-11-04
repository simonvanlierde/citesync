# `write` changes manifests only for fields you list

- Status: accepted
- Date: 2026-10-28

## Context

Citation files exist to hold this metadata, so `write` may rewrite them freely. A package manifest is different: a release tool often owns its version, and a rewrite can fight that tool.

## Decision

`write` always updates citation files that are not the source. It changes a manifest only for the fields in `write-manifests`, or for every writable field with `"all"`, which suits repos with no release tool. The default is none.

`write` changes values already there and never adds a field, so a .zenodo.json without a `version` stays without one. A new citation file is created only when `files` in config lists it.

## Consequences

- A default `write` cannot disturb a release tool.
- A manifest finding that `write` may not fix is reported with what to do: edit by hand, or add the field to `write-manifests`.
- Details are in [How write works](../write.md) and [Configuration](../config.md).

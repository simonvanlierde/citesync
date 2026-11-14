# Design decisions

These records explain choices that shape citesync, their reasons and their consequences. Each decision below is accepted.

- [Any supported file can be the source](0001-pluggable-source.md).
- [Field locations come from a vendored mapping](0002-vendored-mapping.md).
- [Write changes only the manifest fields you select](0003-manifests-opt-in.md).
- [Use Python 3.13 and ruamel.yaml](0004-python-and-ruamel.md).
- [Keep contribution roles intact without interpreting them](0005-vocabulary-blind-roles.md).

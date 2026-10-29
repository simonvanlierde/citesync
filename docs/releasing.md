# Releasing

To release, add a `## [X.Y.Z]` section to `CHANGELOG.md`, then push the tag `vX.Y.Z`.
`python-release.yml` publishes to PyPI, then creates the GitHub release with the distributions and their provenance bundle.
Approve the `pypi` environment when prompted. Do not create the GitHub release by hand.
If the release job fails after PyPI succeeds, delete any leftover draft with `gh release delete vX.Y.Z`.
Re-run only the `release` job. A published immutable release needs a new patch version to fix its files.

Before the first release, set up the publishing environment
(`pypi`)
in Settings > Environments: limit it to tags matching `v*`, and add a required reviewer.
The release workflows explain the rest in their header comments.

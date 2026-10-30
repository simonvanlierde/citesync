# Releasing

1. Add a `## [X.Y.Z]` section to `CHANGELOG.md`.
2. Push the tag `vX.Y.Z`. `python-release.yml` publishes to PyPI, then creates the GitHub release with the distributions and their provenance bundle.
3. Approve the `pypi` environment when prompted.

Don't create the GitHub release by hand. If the release job fails after PyPI succeeds, delete any leftover draft with `gh release delete vX.Y.Z`, then re-run only the `release` job. Once a release is published, its files can't change: fixing them takes a new patch version.

Before the first release, set up the `pypi` environment in Settings > Environments. Limit it to tags matching `v*`, and add a required reviewer. The release workflows explain the rest in their header comments.

# Getting started

Install citesync with [uv](https://docs.astral.sh/uv/), then run a first check from your repository:

```sh
uv tool install citesync
citesync check
```

Python 3.13 or newer is required. To run a check without installing citesync, use `uvx citesync check`. To uninstall it, run `uv tool uninstall citesync`.

## Create your citation file

If your repository has package metadata but no CITATION.cff, create one and review it:

```sh
citesync init
citesync check
```

[The init guide](init.md) explains where each field comes from. To work without Python, [use the browser playground](../playground/README.md) instead.

## Review and fix differences

A check compares the metadata files with CITATION.cff by default. Select another source explicitly when needed:

```sh
citesync check --source pyproject.toml
citesync write --diff
citesync write
```

Review the preview before writing. The [write guide](write.md) explains which files and fields can change. The [check guide](check.md) explains findings and exit codes.

## Add checks to your workflow

[Set up the pre-commit hook](../README.md#pre-commit-hook) for repeatable checks. [Require selected fields](config.md#require-values-in-selected-files) when a release needs authors, licences or a DOI. For data releases, [keep software and dataset metadata separate](datasets.md).

## Verify a release download

Use [GitHub CLI](https://cli.github.com/) to download a wheel and its provenance bundle from the same release. These commands check version 0.6.0. Change the tag and filenames together for another release.

```sh
gh release download v0.6.0 --repo simonvanlierde/citesync \
  --pattern 'citesync-0.6.0-py3-none-any.whl*'
gh attestation verify citesync-0.6.0-py3-none-any.whl \
  --bundle citesync-0.6.0-py3-none-any.whl.intoto.jsonl \
  --repo simonvanlierde/citesync \
  --signer-workflow simonvanlierde/citesync/.github/workflows/python-release.yml \
  --source-ref refs/tags/v0.6.0
```

GitHub CLI checks the artifact digest and signature using the [Sigstore trust roots](https://docs.sigstore.dev/cosign/signing/overview/). A successful check shows the repository, the release workflow and the tag. If verification fails, do not install the download. The source archive and the software bill of materials have their own `.intoto.jsonl` bundles on the [release page](https://github.com/simonvanlierde/citesync/releases).

From a clean clone on `main`, you can also check the signed Git tag against the repository's [authorized signing keys](../.github/allowed_signers).

```sh
git fetch origin tag v0.6.0 &&
  git -c gpg.ssh.allowedSignersFile=.github/allowed_signers verify-tag v0.6.0
```

# Architecture and security

citesync reads repository metadata and turns it into one record for comparison or export. The readers take field locations from the [pinned CodeMeta mapping](decisions/0002-vendored-mapping.md). The comparison rules report differences. The writers use the same record to create citations or update fields in selected files. The CLI and pre-commit hook run this Python code locally. The playground runs it in a browser worker through Pyodide.

## Security boundaries

| What can go wrong | How citesync handles it | Where to check |
| --- | --- | --- |
| A metadata file or symlink names a path outside the repository. | The reader checks that the resolved metadata path stays inside the repository. The writer checks each destination before changing it. | [Path tests](../tests/test_write.py) |
| A package manifest contains code or malformed data. | Readers parse supported formats as data. They check names, versions and input structure where the format requires it. Invalid input produces a finding or an error. | [Supported formats](formats.md), [reader tests](../tests/test_read.py) |
| A playground input leaks to a server or runs in the page. | The worker accepts supported filenames and up to 1 MB of text per input. Each conversion uses a new temporary directory in the browser. The page renders output as text. Drafts stay in memory. Browser tests check network requests and storage for draft data. | [Playground guide](../playground/README.md), [input tests](../tests/test_playground.py), [browser tests](../playground/ui.spec.mjs) |
| A stale or changed package reaches the playground runtime. | The worker checks each wheel against the SHA-256 digest in the site's runtime manifest before loading it. The playground trusts the published site and downloads Pyodide from jsDelivr. | [Worker](../playground/worker.mjs) |
| A build publishes untested files or a download changes after signing. | The release workflow checks the signed tag, tests the wheel, and publishes through PyPI Trusted Publishing. Its publish job runs no project code. The workflow verifies the signed provenance of the release files before publishing the GitHub release. | [Release workflow](../.github/workflows/python-release.yml), [verify a download](getting-started.md#verify-a-release-download) |

Before running `citesync write` on a repository you received from someone else, use `citesync write --diff` and review the changes. Review generated citations before publishing or importing them. CiteSync checks metadata consistency and supported formats. The original metadata and cited claims still need a source you trust.

The project checks Python dependencies with a scheduled audit and checks pull requests for new dependency advisories. GitHub CodeQL and the git hooks check the code and workflows. To report a security problem, use the [private reporting process](../.github/SECURITY.md).

## Development through November 2027

- Publish 0.7.0 with read-only Composer and Maven imports, then submit CiteSync to the Research Software Directory.
- Recheck Software Heritage's support for CodeMeta 4.0 by April 2027. Use the newer context by default when the indexer supports it.
- Work through the [OpenSSF Silver criteria](https://www.bestpractices.dev/en/criteria/1) and maintain the evidence for dependency checks, tests and release verification.
- Run an outside pilot if a participating project volunteers. Publish an example from the pilot with the project's agreement.

The [roadmap’s design boundaries](roadmap.md) also apply through November 2027.

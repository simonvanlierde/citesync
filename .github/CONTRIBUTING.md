# Contributing

Thank you for your interest in citesync. Bug reports, feature requests and pull
requests are welcome. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) first, and
report vulnerabilities as [SECURITY.md](SECURITY.md) describes, not in a public issue.

## Report a bug or ask for a feature

Open an [issue](https://github.com/simonvanlierde/citesync/issues) with the bug or
feature form. For a bug, say what you did, what you expected and what happened, with the
version you used. A question the README and docs don't answer is a gap in the docs: open
a feature request for it.

## Scope and response

One person maintains citesync, in their own time. Expect a reply to an issue or
pull request within about two weeks.

Before a large pull request, such as a new feature or a change to how something works,
open an issue and agree on the change there first. A small fix needs no issue. A pull
request outside what the project sets out to do is closed with a link to this section.

## Set up and check

[Development](../README.md#development) in the README installs the tools, the dependencies
and the git hooks. `just check` runs the checks CI runs, and `just fmt` fixes and
formats.

## When you change a compared field

1. Change its comparison and message in `src/citesync/rules.py`. Keep normalisation detail only there.
2. Change its row in `src/citesync/mapping-local.json` if where the field sits in a file changes.
3. Update the fixtures: `uv run pytest --update-expected` rewrites the expected `cases.json` and `record.json` from actual output. Read the git diff before you commit. [tests/fixtures/README.md](../tests/fixtures/README.md) says how the files are made.
4. Update the docs. `docs/config.md` lists the fields, and `tests/test_docs.py` fails if one is missing there.
5. Run `just mutation`, as the README describes.

## Write commits and pull requests

- **Commits** follow [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/):
  `type(scope): summary`, in the imperative, lower case, with no period. Add a body only
  when the change needs one, with a bullet per logical chunk.
- **The pull request title** becomes the squash commit subject, so it follows the same rule.
- **Both are checked** against [`committed.toml`](../committed.toml): a commit-msg
  hook (installed by `prek install`) refuses a commit message that breaks the rule, and
  the `pull request title` check fails a pull request whose title does. Lower case isn't
  checked. A revert is titled `revert: <original subject>`: rename the
  `Revert "..."` title that GitHub's Revert button writes.
- **The pull request body** has the shape of
  [the pull request template](pull_request_template.md): what it fixes and why, three or
  four bullets, and a `Tests:` line.
- **The changelog** ([CHANGELOG.md](../CHANGELOG.md)) follows
  [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/). Write each entry for
  the people who use the project, not as a commit subject. Mark breaking changes
  **Breaking**, and put upgrade steps first under the version.
- **The release notes** are that version's changelog section.

## Sign off your commits

Every commit in a pull request carries a `Signed-off-by:` line, which says you wrote the
change or have the right to submit it under this project's license: the
[Developer Certificate of Origin 1.1](https://developercertificate.org/). `git commit -s`
adds the line. To add it to commits you already made, run
`git rebase --signoff upstream/main` (the branch you started from) and force-push the branch.

The `dco` workflow checks every pull request from a fork and fails on a commit without the line. Pull requests from a branch in this repository skip it: pushing that branch already needed write access.

## Who maintains this

Simon van Lierde maintains citesync: reviews pull requests, merges them and
makes releases. The repository belongs to [simonvanlierde](https://github.com/simonvanlierde)
on GitHub. A release sets the version in pyproject.toml, adds a `## [X.Y.Z]` section to CHANGELOG.md and pushes the tag `vX.Y.Z`;
the [release workflow](https://github.com/simonvanlierde/project-templates/blob/main/docs/tooling.md#release-workflows) does the rest.
Only maintainers can merge to `main`. A new maintainer is added by an existing one, by name in this section.
If no maintainer can continue, the repository is archived with a note in the README,
and anyone may fork it under its license.
